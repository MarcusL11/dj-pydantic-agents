"""One turn from the first message to the reply, through the public entry points."""

from typing import TYPE_CHECKING
from unittest import mock

from dj_pydantic_agents.composition import build_conversation_command_service
from dj_pydantic_agents.composition import build_conversation_query_service
from dj_pydantic_agents.dtos.conversation_queries import GetConversationPageQueryDTO
from dj_pydantic_agents.dtos.turn_commands import CreateConversationCommandDTO
from dj_pydantic_agents.dtos.turn_commands import DecideApprovalCommandDTO
from dj_pydantic_agents.dtos.turn_commands import StartTurnCommandDTO
from dj_pydantic_agents.entry import run_turn
from dj_pydantic_agents.kit.events import ApprovalRequestedEventDTO
from dj_pydantic_agents.kit.events import TurnDoneEventDTO
from dj_pydantic_agents.kit.transcript import TranscriptLineDTO
from dj_pydantic_agents.models import Turn
from tests.factories import UserFactory
from tests.fakes import FakeModelFactory
from tests.fakes import FakeTaskRunner
from tests.fakes import FakeTransport
from tests.kit.fakes import approval_model
from tests.testcases import TestCase

if TYPE_CHECKING:
    from django.contrib.auth.models import User


class TestTurnFlow(TestCase):
    owner: User

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create(is_staff=True)

    def setUp(self):
        FakeTransport.reset()
        FakeTaskRunner.reset()
        model = approval_model(
            tool_name="send_mail",
            args_json='{"to":"ada"}',
            reply="Done:",
        )
        self.enterContext(mock.patch.object(FakeModelFactory, "model", model))

    def test_a_message_with_an_approval_gets_a_reply(self):
        commands = build_conversation_command_service()
        conversation = commands.create_conversation(
            command=CreateConversationCommandDTO(
                owner_id=self.owner.pk,
                agent_name="assistant",
            ),
        )
        started = commands.start_turn(
            command=StartTurnCommandDTO(
                conversation_id=conversation.conversation_id,
                user_id=self.owner.pk,
                prompt="Mail Ada",
            ),
        )
        assert FakeTaskRunner.turn_ids == [started.turn_id]

        run_turn(started.turn_id)

        page = self.page(conversation.conversation_id)
        assert page.active_turn is not None
        assert page.active_turn.status == "waiting_approval"
        assert isinstance(FakeTransport.events[-1][1], ApprovalRequestedEventDTO)
        (approval,) = page.approvals

        commands.decide_approval(
            command=DecideApprovalCommandDTO(
                approval_id=approval.approval_id,
                user_id=self.owner.pk,
                approved=True,
            ),
        )
        assert FakeTaskRunner.turn_ids == [started.turn_id, started.turn_id]

        run_turn(started.turn_id)

        page = self.page(conversation.conversation_id)
        turn = Turn.objects.get(id=started.turn_id)
        assert page.title == "Mail Ada"
        assert page.active_turn is None
        assert page.lines == (
            TranscriptLineDTO(kind="user", text="Mail Ada"),
            TranscriptLineDTO(
                kind="tool_call",
                text='{"to":"ada"}',
                tool_name="send_mail",
            ),
            TranscriptLineDTO(
                kind="tool_result",
                text="sent to ada",
                tool_name="send_mail",
            ),
            TranscriptLineDTO(kind="assistant", text="Done: sent to ada"),
        )
        assert FakeTransport.events[-1] == (
            started.turn_id,
            TurnDoneEventDTO(text="Done: sent to ada"),
        )
        assert turn.status == Turn.Status.DONE
        assert turn.requests == 2  # noqa: PLR2004 - one request in each run
        assert turn.tool_calls == 1

    def page(self, conversation_id: str):
        return build_conversation_query_service().get_conversation_page(
            query=GetConversationPageQueryDTO(
                conversation_id=conversation_id,
                user_id=self.owner.pk,
            ),
        )
