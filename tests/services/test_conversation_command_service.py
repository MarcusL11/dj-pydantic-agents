from unittest.mock import create_autospec

from dj_pydantic_agents.dtos.conversation_queries import GetApprovalAgentQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import GetConversationAgentQueryDTO
from dj_pydantic_agents.dtos.turn_commands import ConversationCreatedResultDTO
from dj_pydantic_agents.dtos.turn_commands import CreateConversationCommandDTO
from dj_pydantic_agents.dtos.turn_commands import DecideApprovalCommandDTO
from dj_pydantic_agents.dtos.turn_commands import FailTurnCommandDTO
from dj_pydantic_agents.dtos.turn_commands import StartTurnCommandDTO
from dj_pydantic_agents.dtos.turn_events import ApprovalDecidedEventDTO
from dj_pydantic_agents.errors import AgentAccessDenied
from dj_pydantic_agents.errors import AgentNotFound
from dj_pydantic_agents.permissions import StaffPermission
from dj_pydantic_agents.repositories.conversation_query_repository import (
    ConversationQueryRepository,
)
from dj_pydantic_agents.repositories.turn_command_repository import (
    TurnCommandRepository,
)
from dj_pydantic_agents.services.conversation_command_service import (
    ConversationCommandService,
)
from dj_pydantic_agents.signals import approval_decided
from tests.builders import APPROVAL_ID
from tests.builders import CONVERSATION_ID
from tests.builders import TURN_ID
from tests.builders import USER_ID
from tests.builders import a_decided_result
from tests.builders import a_started_result
from tests.builders import an_agent
from tests.fakes import ASSISTANT_SPEC
from tests.fakes import FakeTaskRunner
from tests.testcases import SimpleTestCase

START_COMMAND = StartTurnCommandDTO(
    conversation_id=CONVERSATION_ID,
    user_id=USER_ID,
    prompt="Hi",
)
DECIDE_COMMAND = DecideApprovalCommandDTO(
    approval_id=APPROVAL_ID,
    user_id=USER_ID,
    approved=True,
)


class TestConversationCommandService(SimpleTestCase):
    def setUp(self):
        self.repository = create_autospec(TurnCommandRepository, instance=True)
        self.queries = create_autospec(ConversationQueryRepository, instance=True)
        self.queries.get_conversation_agent.return_value = an_agent()
        self.queries.get_approval_agent.return_value = an_agent()
        self.permission = create_autospec(StaffPermission, instance=True)
        self.permission.can_use.return_value = True
        self.task_runner = create_autospec(FakeTaskRunner, instance=True)
        self.service = ConversationCommandService(
            repository=self.repository,
            queries=self.queries,
            specs={"assistant": ASSISTANT_SPEC},
            permission=self.permission,
            task_runner=self.task_runner,
        )

    def test_creates_a_conversation_for_a_known_agent(self):
        command = CreateConversationCommandDTO(owner_id=USER_ID, agent_name="assistant")
        created = ConversationCreatedResultDTO(conversation_id=CONVERSATION_ID)
        self.repository.create_conversation.return_value = created

        assert self.service.create_conversation(command=command) == created
        self.permission.can_use.assert_called_once_with(
            user_id=USER_ID,
            agent_name="assistant",
        )

    def test_an_unknown_agent_creates_nothing(self):
        command = CreateConversationCommandDTO(owner_id=USER_ID, agent_name="other")

        with self.assertRaises(AgentNotFound):
            self.service.create_conversation(command=command)

        self.repository.create_conversation.assert_not_called()

    def test_a_denied_user_creates_nothing(self):
        self.permission.can_use.return_value = False
        command = CreateConversationCommandDTO(owner_id=USER_ID, agent_name="assistant")

        with self.assertRaises(AgentAccessDenied):
            self.service.create_conversation(command=command)

        self.repository.create_conversation.assert_not_called()

    def test_start_turn_queues_the_turn_after_the_write(self):
        self.repository.start_turn.return_value = a_started_result()

        result = self.service.start_turn(command=START_COMMAND)

        assert result == a_started_result()
        self.queries.get_conversation_agent.assert_called_once_with(
            query=GetConversationAgentQueryDTO(
                conversation_id=CONVERSATION_ID,
                user_id=USER_ID,
            ),
        )
        self.repository.start_turn.assert_called_once_with(command=START_COMMAND)
        self.task_runner.enqueue.assert_called_once_with(turn_id=TURN_ID)

    def test_a_denied_user_starts_no_turn(self):
        self.permission.can_use.return_value = False

        with self.assertRaises(AgentAccessDenied):
            self.service.start_turn(command=START_COMMAND)

        self.repository.start_turn.assert_not_called()
        self.task_runner.enqueue.assert_not_called()

    def test_a_refused_task_fails_the_turn(self):
        self.repository.start_turn.return_value = a_started_result()
        self.task_runner.enqueue.side_effect = ConnectionError("No broker")

        with self.assertRaises(ConnectionError):
            self.service.start_turn(command=START_COMMAND)

        self.repository.fail_turn.assert_called_once_with(
            command=FailTurnCommandDTO(turn_id=TURN_ID, error_code="enqueue_failed"),
        )

    def test_a_decision_waits_for_the_others(self):
        self.repository.decide_approval.return_value = a_decided_result()
        events = self.capture_decisions()

        result = self.service.decide_approval(command=DECIDE_COMMAND)

        assert result == a_decided_result()
        self.queries.get_approval_agent.assert_called_once_with(
            query=GetApprovalAgentQueryDTO(approval_id=APPROVAL_ID, user_id=USER_ID),
        )
        self.task_runner.enqueue.assert_not_called()
        assert events == [
            ApprovalDecidedEventDTO(
                approval_id=APPROVAL_ID,
                turn_id=TURN_ID,
                user_id=USER_ID,
                approved=True,
            ),
        ]

    def test_the_last_decision_queues_the_turn(self):
        self.repository.decide_approval.return_value = a_decided_result(requeued=True)

        self.service.decide_approval(command=DECIDE_COMMAND)

        self.task_runner.enqueue.assert_called_once_with(turn_id=TURN_ID)

    def test_a_denied_user_decides_nothing(self):
        self.permission.can_use.return_value = False
        events = self.capture_decisions()

        with self.assertRaises(AgentAccessDenied):
            self.service.decide_approval(command=DECIDE_COMMAND)

        self.repository.decide_approval.assert_not_called()
        assert events == []

    def capture_decisions(self) -> list[ApprovalDecidedEventDTO]:
        events: list[ApprovalDecidedEventDTO] = []

        def receive(*, event, **_kwargs):
            events.append(event)

        approval_decided.connect(receive, weak=False)
        self.addCleanup(approval_decided.disconnect, receive)
        return events
