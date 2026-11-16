"""Create conversations, send messages and decide approvals."""

# create_autospec() reads the annotations of each method, so the annotation
# types load at runtime.
# ruff: noqa: TC001, TC003

from collections.abc import Mapping

from dj_pydantic_agents.dtos.conversation_queries import GetApprovalAgentQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import GetConversationAgentQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import GetTurnAgentQueryDTO
from dj_pydantic_agents.dtos.turn_commands import ApprovalDecidedResultDTO
from dj_pydantic_agents.dtos.turn_commands import ConversationCreatedResultDTO
from dj_pydantic_agents.dtos.turn_commands import CreateConversationCommandDTO
from dj_pydantic_agents.dtos.turn_commands import DecideApprovalCommandDTO
from dj_pydantic_agents.dtos.turn_commands import FailStaleTurnCommandDTO
from dj_pydantic_agents.dtos.turn_commands import FailTurnCommandDTO
from dj_pydantic_agents.dtos.turn_commands import StartTurnCommandDTO
from dj_pydantic_agents.dtos.turn_commands import TurnStartedResultDTO
from dj_pydantic_agents.dtos.turn_commands import UserId
from dj_pydantic_agents.dtos.turn_events import ApprovalDecidedEventDTO
from dj_pydantic_agents.dtos.turn_streams import GetTurnSnapshotQueryDTO
from dj_pydantic_agents.dtos.turn_streams import OpenTurnStreamCommandDTO
from dj_pydantic_agents.dtos.turn_streams import TurnSnapshotProjectionDTO
from dj_pydantic_agents.errors import AgentAccessDenied
from dj_pydantic_agents.errors import AgentNotFound
from dj_pydantic_agents.errors import TurnNotQueued
from dj_pydantic_agents.extensions import AgentPermission
from dj_pydantic_agents.extensions import TaskRunner
from dj_pydantic_agents.kit.specs import AgentSpec
from dj_pydantic_agents.repositories.conversation_query_repository import (
    ConversationQueryRepository,
)
from dj_pydantic_agents.repositories.turn_command_repository import (
    TurnCommandRepository,
)
from dj_pydantic_agents.signals import approval_decided
from dj_pydantic_agents.signals import send_hook

# The error code of a turn that the task runner did not take.
ENQUEUE_FAILED = TurnNotQueued.error_code
# The error code of a queued or running turn that stayed too long in its status.
WORKER_LOST = "worker_lost"


class ConversationCommandService:
    def __init__(  # noqa: PLR0913
        self,
        *,
        repository: TurnCommandRepository,
        queries: ConversationQueryRepository,
        specs: Mapping[str, AgentSpec],
        permission: AgentPermission,
        task_runner: TaskRunner,
        stale_turn_seconds: int,
    ) -> None:
        self._repository = repository
        self._queries = queries
        self._specs = specs
        self._permission = permission
        self._task_runner = task_runner
        self._stale_turn_seconds = stale_turn_seconds

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
        self._enqueue(turn_id=result.turn_id, conversation_id=result.conversation_id)
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
            self._enqueue(
                turn_id=result.turn_id,
                conversation_id=result.conversation_id,
            )
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

    def open_turn_stream(
        self,
        *,
        command: OpenTurnStreamCommandDTO,
    ) -> TurnSnapshotProjectionDTO:
        """Read the state of a turn for a stream. First fail it if it is stale.

        A stale turn lost its worker, for example after a crash or a hard time
        limit. The check runs only when a stream opens.
        """
        agent = self._queries.get_turn_agent(
            query=GetTurnAgentQueryDTO(
                turn_id=command.turn_id,
                user_id=command.user_id,
            ),
        )
        self._check_access(user_id=command.user_id, agent_name=agent.agent_name)
        self._repository.fail_stale_turn(
            command=FailStaleTurnCommandDTO(
                turn_id=command.turn_id,
                stale_seconds=self._stale_turn_seconds,
                error_code=WORKER_LOST,
            ),
        )
        return self._queries.get_turn_snapshot(
            query=GetTurnSnapshotQueryDTO(
                turn_id=command.turn_id,
                user_id=command.user_id,
            ),
        )

    def _check_access(self, *, user_id: UserId, agent_name: str) -> None:
        if agent_name not in self._specs:
            msg = f"No agent has the name {agent_name!r}."
            raise AgentNotFound(msg)
        if not self._permission.can_use(user_id=user_id, agent_name=agent_name):
            msg = f"The user cannot use the agent {agent_name!r}."
            raise AgentAccessDenied(msg)

    def _enqueue(self, *, turn_id: str, conversation_id: str) -> None:
        """Fail the turn if the task runner refuses it.

        Else the turn stays active, and the conversation takes no more messages.
        """
        try:
            self._task_runner.enqueue(turn_id=turn_id)
        except Exception as error:
            self._repository.fail_turn(
                command=FailTurnCommandDTO(turn_id=turn_id, error_code=ENQUEUE_FAILED),
            )
            msg = "The task runner did not take the turn."
            raise TurnNotQueued(
                msg,
                turn_id=turn_id,
                conversation_id=conversation_id,
            ) from error
