from typing import Any
from unittest.mock import create_autospec

from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import BinaryContent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.messages import ModelRequest
from pydantic_ai.messages import UserContent
from pydantic_ai.messages import UserPromptPart
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits

from dj_pydantic_agents.dtos.turn_commands import ClaimTurnCommandDTO
from dj_pydantic_agents.dtos.turn_commands import FailTurnCommandDTO
from dj_pydantic_agents.dtos.turn_commands import RunTurnCommandDTO
from dj_pydantic_agents.dtos.turn_commands import TurnUsageDTO
from dj_pydantic_agents.dtos.turn_events import TurnFinishedEventDTO
from dj_pydantic_agents.errors import TurnStateConflict
from dj_pydantic_agents.kit.events import ApprovalRequestedEventDTO
from dj_pydantic_agents.kit.events import PendingApprovalDTO
from dj_pydantic_agents.kit.events import TextDeltaEventDTO
from dj_pydantic_agents.kit.events import ToolCallEventDTO
from dj_pydantic_agents.kit.events import TurnDoneEventDTO
from dj_pydantic_agents.kit.events import TurnFailedEventDTO
from dj_pydantic_agents.kit.history import messages_to_json
from dj_pydantic_agents.kit.runner import TurnRunner
from dj_pydantic_agents.repositories.turn_command_repository import (
    TurnCommandRepository,
)
from dj_pydantic_agents.services.turn_run_service import TurnRunService
from dj_pydantic_agents.signals import turn_finished
from tests.builders import CONVERSATION_ID
from tests.builders import FILE_ID
from tests.builders import TURN_ID
from tests.builders import USER_ID
from tests.builders import a_prompt_file
from tests.builders import a_run_input
from tests.builders import a_saved_result
from tests.fakes import ASSISTANT_SPEC
from tests.fakes import FakeModelFactory
from tests.fakes import FakePromptFiles
from tests.fakes import FakeTransport
from tests.kit.fakes import approval_model
from tests.kit.fakes import text_model
from tests.testcases import SimpleTestCase

SEND_MAIL_APPROVAL = PendingApprovalDTO(
    tool_call_id="call-1",
    tool_name="send_mail",
    args_json='{"to":"ada"}',
)
PDF_BYTES = b"%PDF-1.7 invoice"
EARLIER_TURN_ID = "trn_earlier"


def recording_model(requests: list[list[ModelMessage]]) -> FunctionModel:
    """A model that keeps the messages of each request and replies "Read"."""

    async def stream(messages: list[ModelMessage], _info: AgentInfo):
        requests.append(messages)
        yield "Read"

    return FunctionModel(stream_function=stream)


def prompt_contents(messages: list[ModelMessage]) -> list[Any]:
    return [
        part.content
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    ]


def stored_prompt(*, text: str) -> list[Any]:
    """The stored JSON of a first run with one PDF: the file has no data."""
    prompt: list[UserContent] = [
        text,
        "Attached file: invoice.pdf",
        BinaryContent(data=b"", media_type="application/pdf", identifier=FILE_ID),
    ]
    return messages_to_json([ModelRequest(parts=[UserPromptPart(content=prompt)])])


class TestTurnRunService(SimpleTestCase):
    def setUp(self):
        self.repository = create_autospec(TurnCommandRepository, instance=True)
        self.repository.claim_turn.return_value = a_run_input()
        self.repository.save_turn_result.return_value = a_saved_result()
        self.model_factory = create_autospec(FakeModelFactory, instance=True)
        self.model_factory.build.return_value = text_model("Hello", " there")
        self.deps_calls: list[dict[str, object]] = []
        self.prompt_files = create_autospec(FakePromptFiles, instance=True)
        self.prompt_files.load.return_value = ()
        FakeTransport.reset()
        self.finished: list[TurnFinishedEventDTO] = []
        turn_finished.connect(self.on_finished)
        self.addCleanup(turn_finished.disconnect, self.on_finished)

    def on_finished(self, *, event, **_kwargs):
        self.finished.append(event)

    def build_deps(self, **kwargs):
        self.deps_calls.append(kwargs)

    def run_turn(self, *, usage_limits=None, with_files=True):
        TurnRunService(
            repository=self.repository,
            specs={"assistant": ASSISTANT_SPEC},
            deps_factory=self.build_deps,
            model_factory=self.model_factory,
            transport=FakeTransport(),
            runner=TurnRunner(),
            usage_limits=usage_limits,
            prompt_files=self.prompt_files if with_files else None,
            file_history_turns=3,
        ).run_turn(command=RunTurnCommandDTO(turn_id=TURN_ID))

    def test_the_files_of_the_turn_go_to_the_model_but_not_to_the_history(self):
        self.repository.claim_turn.return_value = a_run_input(
            prompt="Read this",
            recent_turn_ids=(TURN_ID, EARLIER_TURN_ID),
        )
        self.prompt_files.load.return_value = (a_prompt_file(data=PDF_BYTES),)
        requests: list[list[ModelMessage]] = []
        self.model_factory.build.return_value = recording_model(requests)

        self.run_turn()

        self.prompt_files.load.assert_called_once_with(
            turn_ids=(TURN_ID, EARLIER_TURN_ID),
        )
        [sent] = prompt_contents(requests[0])
        assert sent[:2] == ["Read this", "Attached file: invoice.pdf"]
        assert (sent[2].data, sent[2].identifier) == (PDF_BYTES, FILE_ID)
        saved = self.saved_command().new_messages[0]["parts"][0]["content"]
        assert saved == stored_prompt(text="Read this")[0]["parts"][0]["content"]

    def test_a_later_turn_sends_the_file_of_a_recent_turn_again(self):
        self.repository.claim_turn.return_value = a_run_input(
            prompt="And the total?",
            history=tuple(stored_prompt(text="Read this")),
            recent_turn_ids=(TURN_ID, EARLIER_TURN_ID),
        )
        self.prompt_files.load.return_value = (
            a_prompt_file(turn_id=EARLIER_TURN_ID, data=PDF_BYTES),
        )
        requests: list[list[ModelMessage]] = []
        self.model_factory.build.return_value = recording_model(requests)

        self.run_turn()

        earlier, current = prompt_contents(requests[0])
        assert earlier[2].data == PDF_BYTES
        assert current == "And the total?"

    def test_an_old_file_stays_out_and_its_label_says_so(self):
        self.repository.claim_turn.return_value = a_run_input(
            prompt="Thanks",
            history=tuple(stored_prompt(text="Read this")),
            recent_turn_ids=(TURN_ID,),
        )
        requests: list[list[ModelMessage]] = []
        self.model_factory.build.return_value = recording_model(requests)

        self.run_turn()

        earlier, _current = prompt_contents(requests[0])
        assert earlier == [
            "Read this",
            "Attached file: invoice.pdf (from an earlier message. "
            "The file is not in this request.)",
        ]

    def test_a_chat_with_no_prompt_files_loads_no_files(self):
        self.repository.claim_turn.return_value = a_run_input(
            recent_turn_ids=(TURN_ID,),
        )

        self.run_turn(with_files=False)

        self.prompt_files.load.assert_not_called()
        self.repository.save_turn_result.assert_called_once()

    def test_a_failed_load_fails_the_turn(self):
        self.repository.claim_turn.return_value = a_run_input(
            recent_turn_ids=(TURN_ID,),
        )
        self.prompt_files.load.side_effect = FileNotFoundError

        with self.assertLogs("dj_pydantic_agents", level="ERROR"):
            self.run_turn()

        self.repository.save_turn_result.assert_not_called()
        self.repository.fail_turn.assert_called_once()

    def saved_command(self):
        return self.repository.save_turn_result.call_args.kwargs["command"]

    def finished_event(self, **overrides):
        values = {
            "turn_id": TURN_ID,
            "conversation_id": CONVERSATION_ID,
            "agent_name": "assistant",
            "user_id": USER_ID,
            "status": "done",
            "error_code": "",
        }
        return TurnFinishedEventDTO(**{**values, **overrides})

    def test_a_reply_saves_the_turn_and_streams_the_text(self):
        self.run_turn()

        self.repository.claim_turn.assert_called_once_with(
            command=ClaimTurnCommandDTO(turn_id=TURN_ID, history_turns=3),
        )
        assert self.deps_calls == [
            {
                "agent_name": "assistant",
                "user_id": USER_ID,
                "conversation_id": CONVERSATION_ID,
            },
        ]
        self.model_factory.build.assert_called_once_with(
            role=ASSISTANT_SPEC.model_role,
            user_id=USER_ID,
        )
        saved = self.saved_command()
        assert [message["kind"] for message in saved.new_messages] == [
            "request",
            "response",
        ]
        assert saved.pending is None
        assert saved.approvals == ()
        assert saved.usage == TurnUsageDTO(
            requests=1,
            input_tokens=saved.usage.input_tokens,
            output_tokens=saved.usage.output_tokens,
        )
        assert FakeTransport.events == [
            (TURN_ID, TextDeltaEventDTO(text="Hello")),
            (TURN_ID, TextDeltaEventDTO(text=" there")),
            (TURN_ID, TurnDoneEventDTO(text="Hello there")),
        ]
        assert self.finished == [self.finished_event()]

    def test_an_approval_stop_saves_the_pending_call(self):
        self.model_factory.build.return_value = approval_model(
            tool_name="send_mail",
            args_json='{"to":"ada"}',
            reply="Done:",
        )
        self.repository.save_turn_result.return_value = a_saved_result(
            status="waiting_approval",
        )

        self.run_turn()

        saved = self.saved_command()
        assert saved.pending is not None
        assert saved.approvals == (SEND_MAIL_APPROVAL,)
        assert FakeTransport.events == [
            (
                TURN_ID,
                ToolCallEventDTO(
                    tool_call_id="call-1",
                    tool_name="send_mail",
                    args_json='{"to":"ada"}',
                ),
            ),
            (TURN_ID, ApprovalRequestedEventDTO(approvals=(SEND_MAIL_APPROVAL,))),
        ]
        assert self.finished == [self.finished_event(status="waiting_approval")]

    def test_a_resume_runs_the_approved_tool(self):
        model = approval_model(
            tool_name="send_mail",
            args_json='{"to":"ada"}',
            reply="Done:",
        )
        self.model_factory.build.return_value = model
        self.repository.save_turn_result.return_value = a_saved_result(
            status="waiting_approval",
        )
        self.run_turn()
        first = self.saved_command()
        self.repository.claim_turn.return_value = a_run_input(
            history=first.new_messages,
            prompt=None,
            pending=first.pending,
            decisions={"call-1": True},
        )
        self.repository.save_turn_result.return_value = a_saved_result()
        FakeTransport.reset()

        self.run_turn()

        assert self.saved_command().approvals == ()
        assert FakeTransport.events[-1] == (
            TURN_ID,
            TurnDoneEventDTO(text="Done: sent to ada"),
        )

    def test_a_turn_that_is_not_queued_does_nothing(self):
        self.repository.claim_turn.return_value = None

        self.run_turn()

        self.repository.save_turn_result.assert_not_called()
        self.repository.fail_turn.assert_not_called()
        assert FakeTransport.events == []
        assert self.finished == []

    def test_a_missing_agent_fails_the_turn(self):
        self.repository.claim_turn.return_value = a_run_input(agent_name="gone")

        with self.assertLogs("dj_pydantic_agents", level="ERROR"):
            self.run_turn()

        self.assert_failed(error_code="agent_not_found", agent_name="gone")

    def test_a_model_error_fails_the_turn_with_its_code(self):
        self.model_factory.build.side_effect = ModelAPIError("test-model", "Down")

        with self.assertLogs("dj_pydantic_agents", level="ERROR"):
            self.run_turn()

        self.assert_failed(error_code="model_api_error")

    def test_the_usage_limits_apply_to_the_run(self):
        with self.assertLogs("dj_pydantic_agents", level="ERROR"):
            self.run_turn(usage_limits=UsageLimits(request_limit=0))

        self.assert_failed(error_code="usage_limit")

    def test_a_save_error_fails_the_turn(self):
        self.repository.save_turn_result.side_effect = TurnStateConflict("Not running")

        with self.assertLogs("dj_pydantic_agents", level="ERROR"):
            self.run_turn()

        self.assert_failed(error_code="internal_error")

    def assert_failed(self, *, error_code, agent_name="assistant"):
        self.repository.fail_turn.assert_called_once_with(
            command=FailTurnCommandDTO(turn_id=TURN_ID, error_code=error_code),
        )
        assert FakeTransport.events[-1] == (
            TURN_ID,
            TurnFailedEventDTO(error_code=error_code),
        )
        assert self.finished == [
            self.finished_event(
                status="failed",
                error_code=error_code,
                agent_name=agent_name,
            ),
        ]

    def test_a_transport_error_does_not_stop_the_turn(self):
        transport = create_autospec(FakeTransport, instance=True)
        transport.publish.side_effect = ConnectionError("Redis is down")

        with self.assertLogs("dj_pydantic_agents", level="ERROR") as logs:
            TurnRunService(
                repository=self.repository,
                specs={"assistant": ASSISTANT_SPEC},
                deps_factory=self.build_deps,
                model_factory=self.model_factory,
                transport=transport,
                runner=TurnRunner(),
            ).run_turn(command=RunTurnCommandDTO(turn_id=TURN_ID))

        self.repository.save_turn_result.assert_called_once()
        self.repository.fail_turn.assert_not_called()
        assert len(logs.records) == transport.publish.call_count
        assert self.finished == [self.finished_event()]

    def test_a_broken_receiver_does_not_stop_the_turn(self):
        def broken(**_kwargs):
            raise RuntimeError

        turn_finished.connect(broken)
        self.addCleanup(turn_finished.disconnect, broken)

        with self.assertLogs("dj_pydantic_agents.signals", level="ERROR"):
            self.run_turn()

        self.repository.fail_turn.assert_not_called()
        assert self.finished == [self.finished_event()]
