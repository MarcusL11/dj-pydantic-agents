from typing import TYPE_CHECKING

from pydantic_ai.messages import ModelRequest
from pydantic_ai.messages import ModelResponse
from pydantic_ai.messages import TextPart
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.messages import UserPromptPart
from pydantic_ai.tools import DeferredToolRequests

from dj_pydantic_agents.dtos.conversation_queries import ActiveTurnProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import ApprovalProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import GetConversationPageQueryDTO
from dj_pydantic_agents.errors import ConversationNotFound
from dj_pydantic_agents.kit.history import messages_to_json
from dj_pydantic_agents.kit.history import pending_to_json
from dj_pydantic_agents.kit.transcript import TranscriptLineDTO
from dj_pydantic_agents.models import Conversation
from dj_pydantic_agents.models import PendingApproval
from dj_pydantic_agents.models import Turn
from dj_pydantic_agents.repositories.conversation_query_repository import (
    ConversationQueryRepository,
)
from tests.factories import ConversationFactory
from tests.factories import PendingApprovalFactory
from tests.factories import TurnFactory
from tests.factories import UserFactory
from tests.testcases import TestCase

if TYPE_CHECKING:
    from django.contrib.auth.models import User

# The conversation and the active turn, then the approvals of a waiting turn.
PAGE_QUERIES = 2
WAITING_PAGE_QUERIES = 3


class TestGetConversationPage(TestCase):
    owner: User
    conversation: Conversation

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create()
        cls.conversation = ConversationFactory.create(
            owner=cls.owner,
            title="Greeting",
            messages=messages_to_json(
                [
                    ModelRequest(parts=[UserPromptPart(content="Hi")]),
                    ModelResponse(parts=[TextPart(content="Hello")]),
                ],
            ),
        )

    def page(self, *, user_id=None):
        return ConversationQueryRepository().get_conversation_page(
            query=GetConversationPageQueryDTO(
                conversation_id=self.conversation.id,
                user_id=self.owner.pk if user_id is None else user_id,
            ),
        )

    def test_maps_the_conversation_and_its_lines(self):
        with self.assertNumQueries(PAGE_QUERIES):
            page = self.page()

        assert page.conversation_id == self.conversation.id
        assert page.agent_name == "assistant"
        assert page.title == "Greeting"
        assert page.lines == (
            TranscriptLineDTO(kind="user", text="Hi"),
            TranscriptLineDTO(kind="assistant", text="Hello"),
        )
        assert page.active_turn is None
        assert page.approvals == ()

    def test_another_user_gets_not_found(self):
        other = UserFactory.create()

        with self.assertRaises(ConversationNotFound):
            self.page(user_id=other.pk)

    def test_a_first_run_shows_its_unsaved_prompt(self):
        turn = TurnFactory.create(
            conversation=self.conversation,
            requested_by=self.owner,
            prompt="How are you?",
            status=Turn.Status.RUNNING,
        )

        page = self.page()

        assert page.active_turn == ActiveTurnProjectionDTO(
            turn_id=turn.id,
            status="running",
            unsaved_prompt="How are you?",
        )

    def test_an_approval_stop_shows_the_pending_approvals(self):
        call = ToolCallPart(tool_name="send_mail", args={}, tool_call_id="call-1")
        self.conversation.pending_approvals = pending_to_json(
            DeferredToolRequests(approvals=[call]),
        )
        self.conversation.save(update_fields=["pending_approvals"])
        turn = TurnFactory.create(
            conversation=self.conversation,
            requested_by=self.owner,
            status=Turn.Status.WAITING_APPROVAL,
        )
        pending = PendingApprovalFactory.create(turn=turn, tool_call_id="call-1")
        PendingApprovalFactory.create(
            turn=turn,
            tool_call_id="call-2",
            decision=PendingApproval.Decision.APPROVED,
        )

        with self.assertNumQueries(WAITING_PAGE_QUERIES):
            page = self.page()

        assert page.active_turn == ActiveTurnProjectionDTO(
            turn_id=turn.id,
            status="waiting_approval",
            unsaved_prompt=None,
        )
        assert page.approvals == (
            ApprovalProjectionDTO(
                approval_id=pending.id,
                tool_name="send_mail",
                args_json='{"to":"ada"}',
            ),
        )
