"""Create conversations, send messages and decide approvals."""

from typing import TYPE_CHECKING

from dj_pydantic_agents.dtos.conversation_queries import GetApprovalAgentQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import GetConversationAgentQueryDTO
from dj_pydantic_agents.dtos.turn_commands import FailTurnCommandDTO
from dj_pydantic_agents.dtos.turn_events import ApprovalDecidedEventDTO
from dj_pydantic_agents.errors import AgentAccessDenied
from dj_pydantic_agents.errors import AgentNotFound
from dj_pydantic_agents.signals import approval_decided
from dj_pydantic_agents.signals import send_hook

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dj_pydantic_agents.dtos.turn_commands import ApprovalDecidedResultDTO
    from dj_pydantic_agents.dtos.turn_commands import ConversationCreatedResultDTO
    from dj_pydantic_agents.dtos.turn_commands import CreateConversationCommandDTO
    from dj_pydantic_agents.dtos.turn_commands import DecideApprovalCommandDTO
    from dj_pydantic_agents.dtos.turn_commands import StartTurnCommandDTO
    from dj_pydantic_agents.dtos.turn_commands import TurnStartedResultDTO
    from dj_pydantic_agents.dtos.turn_commands import UserId
    from dj_pydantic_agents.extensions import AgentPermission
    from dj_pydantic_agents.extensions import TaskRunner
    from dj_pydantic_agents.kit.specs import AgentSpec
    from dj_pydantic_agents.repositories.conversation_query_repository import (
        ConversationQueryRepository,
    )
    from dj_pydantic_agents.repositories.turn_command_repository import (
        TurnCommandRepository,
    )

# The error code of a turn that the task runner did not take.
ENQUEUE_FAILED = "enqueue_failed"


class ConversationCommandService:
    def __init__(
        self,
        *,
        repository: TurnCommandRepository,
        queries: ConversationQueryRepository,
        specs: Mapping[str, AgentSpec],
        permission: AgentPermission,
        task_runner: TaskRunner,
    ) -> None:
        self._repository = repository
        self._queries = queries
        self._specs = specs
        self._permission = permission
        self._task_runner = task_runner

    def create_conversation(
        self,
        *,
        command: CreateConversationCommandDTO,
    ) -> ConversationCreatedResultDTO:
        self._check_access(user_id=command.owner_id, agent_name=command.agent_name)
        return self._repository.create_conversation(command=command)

    def start_turn(self, *, command: StartTurnCommandDTO) -> TurnStartedResultDTO:
        """Queue the message as a new turn, then give the turn to the task runner."""
        # A conversation never changes its agent, so this read can come first.
        agent = self._queries.get_conversation_agent(
            query=GetConversationAgentQueryDTO(
                conversation_id=command.conversation_id,
                user_id=command.user_id,
            ),
        )
        self._check_access(user_id=command.user_id, agent_name=agent.agent_name)
        result = self._repository.start_turn(command=command)
        self._enqueue(turn_id=result.turn_id)
        return result

    def decide_approval(
        self,
        *,
        command: DecideApprovalCommandDTO,
    ) -> ApprovalDecidedResultDTO:
        """Record one decision. After the last decision, the turn runs again."""
        agent = self._queries.get_approval_agent(
            query=GetApprovalAgentQueryDTO(
                approval_id=command.approval_id,
                user_id=command.user_id,
            ),
        )
        self._check_access(user_id=command.user_id, agent_name=agent.agent_name)
        result = self._repository.decide_approval(command=command)
        if result.requeued:
            self._enqueue(turn_id=result.turn_id)
        send_hook(
            approval_decided,
            sender=type(self),
            event=ApprovalDecidedEventDTO(
                approval_id=result.approval_id,
                turn_id=result.turn_id,
                user_id=command.user_id,
                approved=command.approved,
            ),
        )
        return result

    def _check_access(self, *, user_id: UserId, agent_name: str) -> None:
        if agent_name not in self._specs:
            msg = f"No agent has the name {agent_name!r}."
            raise AgentNotFound(msg)
        if not self._permission.can_use(user_id=user_id, agent_name=agent_name):
            msg = f"The user cannot use the agent {agent_name!r}."
            raise AgentAccessDenied(msg)

    def _enqueue(self, *, turn_id: str) -> None:
        """Fail the turn if the task runner refuses it.

        Else the turn stays active, and the conversation takes no more messages.
        """
        try:
            self._task_runner.enqueue(turn_id=turn_id)
        except Exception:
            self._repository.fail_turn(
                command=FailTurnCommandDTO(turn_id=turn_id, error_code=ENQUEUE_FAILED),
            )
            raise
