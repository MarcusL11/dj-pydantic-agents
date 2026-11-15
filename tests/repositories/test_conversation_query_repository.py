from typing import TYPE_CHECKING

from pydantic_ai.messages import ModelRequest
from pydantic_ai.messages import ModelResponse
from pydantic_ai.messages import TextPart
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.messages import UserPromptPart
from pydantic_ai.tools import DeferredToolRequests

from dj_pydantic_agents.dtos.conversation_queries import ActiveTurnProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import AgentNameProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import ApprovalProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import GetApprovalAgentQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import GetConversationAgentQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import GetConversationPageQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import GetTurnAgentQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import ListConversationsQueryDTO
from dj_pydantic_agents.dtos.turn_streams import GetTurnSnapshotQueryDTO
from dj_pydantic_agents.errors import ApprovalNotPending
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
# One query with a subquery for the active turn.
LIST_QUERIES = 1
# The turn, then the decided approvals of a running turn, the messages of a
# done turn, or the messages and the pending approvals of a waiting turn.
RUNNING_SNAPSHOT_QUERIES = 2
DONE_SNAPSHOT_QUERIES = 2
WAITING_SNAPSHOT_QUERIES = 3
FAILED_SNAPSHOT_QUERIES = 1


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


class TestGetAgentNames(TestCase):
    owner: User
    approval: PendingApproval

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create()
        conversation = ConversationFactory.create(owner=cls.owner, agent_name="mail")
        cls.approval = PendingApprovalFactory.create(
            turn=TurnFactory.create(conversation=conversation, requested_by=cls.owner),
        )

    def test_reads_the_agent_of_a_conversation_and_of_an_approval(self):
        repository = ConversationQueryRepository()
        conversation_id = self.approval.turn.conversation_id

        conversation_agent = repository.get_conversation_agent(
            query=GetConversationAgentQueryDTO(
                conversation_id=conversation_id,
                user_id=self.owner.pk,
            ),
        )
        approval_agent = repository.get_approval_agent(
            query=GetApprovalAgentQueryDTO(
                approval_id=self.approval.id,
                user_id=self.owner.pk,
            ),
        )

        assert conversation_agent == AgentNameProjectionDTO(agent_name="mail")
        assert approval_agent == AgentNameProjectionDTO(agent_name="mail")

    def test_another_user_reads_no_agent(self):
        other = UserFactory.create()
        repository = ConversationQueryRepository()

        with self.assertRaises(ConversationNotFound):
            repository.get_conversation_agent(
                query=GetConversationAgentQueryDTO(
                    conversation_id=self.approval.turn.conversation_id,
                    user_id=other.pk,
                ),
            )
        with self.assertRaises(ApprovalNotPending):
            repository.get_approval_agent(
                query=GetApprovalAgentQueryDTO(
                    approval_id=self.approval.id,
                    user_id=other.pk,
                ),
            )


class TestListConversations(TestCase):
    owner: User
    older: Conversation
    newer: Conversation

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create()
        cls.older = ConversationFactory.create(owner=cls.owner, title="Older")
        cls.newer = ConversationFactory.create(owner=cls.owner, title="Newer")
        TurnFactory.create(conversation=cls.newer, status=Turn.Status.RUNNING)
        TurnFactory.create(conversation=cls.older, status=Turn.Status.DONE)
        ConversationFactory.create(owner=cls.owner, agent_name="other")
        ConversationFactory.create(title="Of another user")

    def list_conversations(self):
        return ConversationQueryRepository().list_conversations(
            query=ListConversationsQueryDTO(
                user_id=self.owner.pk,
                agent_name="assistant",
            ),
        )

    def test_lists_the_conversations_of_the_user_with_the_agent_newest_first(self):
        with self.assertNumQueries(LIST_QUERIES):
            conversations = self.list_conversations()

        assert [summary.conversation_id for summary in conversations] == [
            self.newer.id,
            self.older.id,
        ]
        newer, older = conversations
        assert newer.title == "Newer"
        assert newer.updated_at == Conversation.objects.get(id=self.newer.id).updated_at
        assert newer.active_turn_status == "running"
        assert older.active_turn_status is None


class TestGetTurnSnapshot(TestCase):
    owner: User
    conversation: Conversation
    turn: Turn

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create()
        cls.conversation = ConversationFactory.create(
            owner=cls.owner,
            messages=messages_to_json(
                [
                    ModelRequest(parts=[UserPromptPart(content="Hi")]),
                    ModelResponse(parts=[TextPart(content="Hello")]),
                ],
            ),
        )
        cls.turn = TurnFactory.create(
            conversation=cls.conversation,
            requested_by=cls.owner,
            status=Turn.Status.RUNNING,
        )

    def snapshot(self, *, user_id=None):
        return ConversationQueryRepository().get_turn_snapshot(
            query=GetTurnSnapshotQueryDTO(
                turn_id=self.turn.id,
                user_id=self.owner.pk if user_id is None else user_id,
            ),
        )

    def set_status(self, status, **fields):
        Turn.objects.filter(id=self.turn.id).update(status=status, **fields)

    def test_a_running_turn_gives_the_decided_tool_calls(self):
        PendingApprovalFactory.create(
            turn=self.turn,
            tool_call_id="call-1",
            decision=PendingApproval.Decision.APPROVED,
        )

        with self.assertNumQueries(RUNNING_SNAPSHOT_QUERIES):
            snapshot = self.snapshot()

        assert snapshot.turn_id == self.turn.id
        assert snapshot.conversation_id == self.conversation.id
        assert snapshot.status == "running"
        assert snapshot.is_streaming is True
        assert snapshot.reply_text == ""
        assert snapshot.decided_tool_call_ids == ("call-1",)

    def test_a_done_turn_gives_the_reply_text(self):
        self.set_status(Turn.Status.DONE)

        with self.assertNumQueries(DONE_SNAPSHOT_QUERIES):
            snapshot = self.snapshot()

        assert snapshot.status == "done"
        assert snapshot.is_streaming is False
        assert snapshot.reply_text == "Hello"
        assert snapshot.decided_tool_call_ids == ()

    def test_a_waiting_turn_gives_the_pending_approvals(self):
        self.set_status(Turn.Status.WAITING_APPROVAL)
        pending = PendingApprovalFactory.create(turn=self.turn)

        with self.assertNumQueries(WAITING_SNAPSHOT_QUERIES):
            snapshot = self.snapshot()

        assert snapshot.reply_text == "Hello"
        assert snapshot.approvals == (
            ApprovalProjectionDTO(
                approval_id=pending.id,
                tool_name="send_mail",
                args_json='{"to":"ada"}',
            ),
        )

    def test_a_failed_turn_gives_the_error_code(self):
        self.set_status(Turn.Status.FAILED, error_code="worker_lost")

        with self.assertNumQueries(FAILED_SNAPSHOT_QUERIES):
            snapshot = self.snapshot()

        assert snapshot.error_code == "worker_lost"
        assert snapshot.reply_text == ""

    def test_another_user_gets_not_found(self):
        with self.assertRaises(ConversationNotFound):
            self.snapshot(user_id=UserFactory.create().pk)

    def test_reads_the_agent_of_the_turn(self):
        repository = ConversationQueryRepository()

        agent = repository.get_turn_agent(
            query=GetTurnAgentQueryDTO(turn_id=self.turn.id, user_id=self.owner.pk),
        )

        assert agent == AgentNameProjectionDTO(agent_name="assistant")
        with self.assertRaises(ConversationNotFound):
            repository.get_turn_agent(
                query=GetTurnAgentQueryDTO(
                    turn_id=self.turn.id,
                    user_id=UserFactory.create().pk,
                ),
            )
