"""The contracts of the extension points.

A project gives a dotted path for each extension point in DJ_PYDANTIC_AGENTS.
SPECS and DEPS_FACTORY are functions. The other paths are classes, and the
package makes each object with no arguments.
"""

from typing import TYPE_CHECKING
from typing import Protocol

if TYPE_CHECKING:
    from pydantic_ai.models import Model

    from dj_pydantic_agents.dtos.turn_commands import UserId
    from dj_pydantic_agents.kit.events import TurnEventDTO
    from dj_pydantic_agents.kit.roles import ModelRole
    from dj_pydantic_agents.kit.specs import AgentSpec


class SpecsProvider(Protocol):
    """SPECS: return the spec of each agent. Each name must be unique."""

    def __call__(self) -> tuple[AgentSpec, ...]: ...


class DepsFactory(Protocol):
    """DEPS_FACTORY: make the deps of one run. The tools of the agent get them."""

    def __call__(
        self,
        *,
        agent_name: str,
        user_id: UserId,
        conversation_id: str,
    ) -> object: ...


class ModelFactory(Protocol):
    """MODEL_FACTORY: make the model for a role and a user."""

    def build(self, *, role: ModelRole, user_id: UserId) -> Model: ...


class AgentPermission(Protocol):
    """PERMISSION: decide if a user can use an agent."""

    def can_use(self, *, user_id: UserId, agent_name: str) -> bool: ...


class EventTransport(Protocol):
    """EVENT_TRANSPORT: store an event of a turn and return its event ID."""

    def publish(self, *, turn_id: str, event: TurnEventDTO) -> str: ...


class TaskRunner(Protocol):
    """TASK_RUNNER: run entry.run_turn(turn_id) in a worker.

    The task must start after the current transaction commits, for example
    with transaction.on_commit(). Else the worker can start before the turn
    row is visible, and the turn stays in the queue.
    """

    def enqueue(self, *, turn_id: str) -> None: ...
