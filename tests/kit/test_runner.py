from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.usage import RunUsage

from dj_pydantic_agents.kit.events import TextDeltaEventDTO
from dj_pydantic_agents.kit.events import ToolCallEventDTO
from dj_pydantic_agents.kit.events import TurnEventDTO
from dj_pydantic_agents.kit.history import messages_from_json
from dj_pydantic_agents.kit.history import messages_to_json
from dj_pydantic_agents.kit.history import pending_from_json
from dj_pydantic_agents.kit.history import pending_to_json
from dj_pydantic_agents.kit.runner import DENIED_MESSAGE
from dj_pydantic_agents.kit.runner import TurnRunner
from dj_pydantic_agents.kit.specs import AgentSpec
from tests.kit.fakes import approval_model
from tests.kit.fakes import text_model
from tests.testcases import SimpleTestCase

CHAT_SPEC = AgentSpec(name="assistant", instructions="Be brief.")


def send_mail(to: str) -> str:
    return f"sent to {to}"


MAIL_SPEC = AgentSpec(
    name="assistant",
    instructions="Be brief.",
    toolsets=(FunctionToolset([send_mail], requires_approval=True),),
)


class TestTurnRunnerText(SimpleTestCase):
    def test_streams_the_text_and_returns_the_reply(self):
        events: list[TurnEventDTO] = []

        outcome = TurnRunner().run(
            spec=CHAT_SPEC,
            model=text_model("Hello", " there"),
            history=[],
            prompt="Hi",
            pending=None,
            decisions=None,
            deps=None,
            on_event=events.append,
        )

        assert events == [
            TextDeltaEventDTO(text="Hello"),
            TextDeltaEventDTO(text=" there"),
        ]
        assert outcome.reply_text == "Hello there"
        assert outcome.pending_approvals is None
        assert [type(m).__name__ for m in outcome.new_messages] == [
            "ModelRequest",
            "ModelResponse",
        ]

    def test_usage_counts_this_turn_only(self):
        runner = TurnRunner()
        first = runner.run(
            spec=CHAT_SPEC,
            model=TestModel(custom_output_text="One"),
            history=[],
            prompt="Hi",
            pending=None,
            decisions=None,
            deps=None,
            on_event=lambda _event: None,
        )

        second = runner.run(
            spec=CHAT_SPEC,
            model=TestModel(custom_output_text="Two"),
            history=list(first.new_messages),
            prompt="Again",
            pending=None,
            decisions=None,
            deps=None,
            on_event=lambda _event: None,
        )

        assert second.usage.requests == 1
        assert second.reply_text == "Two"

    def test_needs_a_prompt_or_decisions(self):
        with self.assertRaisesRegex(ValueError, "Give a prompt"):
            TurnRunner().run(
                spec=CHAT_SPEC,
                model=TestModel(),
                history=[],
                prompt=None,
                pending=None,
                decisions=None,
                deps=None,
                on_event=lambda _event: None,
            )


class TestTurnRunnerApproval(SimpleTestCase):
    """The full approval flow, with a JSON round trip between the two turns."""

    def setUp(self):
        self.model = approval_model(
            tool_name="send_mail",
            args_json='{"to":"ada"}',
            reply="Done:",
        )
        self.events: list[TurnEventDTO] = []
        self.first = TurnRunner().run(
            spec=MAIL_SPEC,
            model=self.model,
            history=[],
            prompt="Mail Ada",
            pending=None,
            decisions=None,
            deps=None,
            on_event=self.events.append,
        )

    def _continue(self, *, approved: bool):
        stored_history = messages_to_json(list(self.first.new_messages))
        stored_pending = pending_to_json(self.first.pending_approvals)
        return TurnRunner().run(
            spec=MAIL_SPEC,
            model=self.model,
            history=messages_from_json(stored_history),
            prompt=None,
            pending=pending_from_json(stored_pending),
            decisions={"call-1": approved},
            deps=None,
            on_event=self.events.append,
        )

    def test_first_turn_stops_for_approval(self):
        assert self.first.reply_text is None
        assert self.first.pending_approvals is not None
        assert [
            part.tool_call_id for part in self.first.pending_approvals.approvals
        ] == ["call-1"]
        assert self.events == [
            ToolCallEventDTO(
                tool_call_id="call-1",
                tool_name="send_mail",
                args_json='{"to":"ada"}',
            ),
        ]

    def test_approval_runs_the_tool(self):
        second = self._continue(approved=True)

        assert second.reply_text == "Done: sent to ada"
        assert second.pending_approvals is None
        assert second.usage == RunUsage(
            requests=1,
            tool_calls=1,
            input_tokens=second.usage.input_tokens,
            output_tokens=second.usage.output_tokens,
        )

    def test_denial_does_not_run_the_tool(self):
        second = self._continue(approved=False)

        assert second.reply_text == f"Done: {DENIED_MESSAGE}"

    def test_ignores_the_decisions_of_an_earlier_stop(self):
        second = TurnRunner().run(
            spec=MAIL_SPEC,
            model=self.model,
            history=list(self.first.new_messages),
            prompt=None,
            pending=self.first.pending_approvals,
            decisions={"call-0": False, "call-1": True},
            deps=None,
            on_event=self.events.append,
        )

        assert second.reply_text == "Done: sent to ada"

    def test_a_new_prompt_closes_an_open_tool_call(self):
        # The resume failed, so the history ends with a call that has no result.
        second = TurnRunner().run(
            spec=MAIL_SPEC,
            model=text_model("Hello"),
            history=list(self.first.new_messages),
            prompt="Never mind",
            pending=None,
            decisions=None,
            deps=None,
            on_event=self.events.append,
        )

        assert second.reply_text == "Hello"
