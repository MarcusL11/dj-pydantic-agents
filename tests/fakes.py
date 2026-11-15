"""Fake extension objects. The test settings point DJ_PYDANTIC_AGENTS here.

The package makes a new object for each service, so the fakes keep their
records on the class. Each test that reads them calls reset() first.
"""

from collections.abc import AsyncGenerator  # noqa: TC003
from typing import ClassVar

# Runtime imports: create_autospec() reads the annotations of the fakes.
from pydantic_ai.models import Model  # noqa: TC002
from pydantic_ai.toolsets import FunctionToolset

from dj_pydantic_agents.dtos.turn_commands import UserId  # noqa: TC001
from dj_pydantic_agents.kit.events import START_EVENT_ID
from dj_pydantic_agents.kit.events import StreamedTurnEventDTO
from dj_pydantic_agents.kit.events import TurnEventDTO
from dj_pydantic_agents.kit.roles import ModelRole  # noqa: TC001
from dj_pydantic_agents.kit.specs import AgentSpec
from tests.kit.fakes import text_model


def send_mail(to: str) -> str:
    return f"sent to {to}"


ASSISTANT_SPEC = AgentSpec(
    name="assistant",
    instructions="Be brief.",
    toolsets=(FunctionToolset([send_mail], requires_approval=True),),
)


def build_specs() -> tuple[AgentSpec, ...]:
    return (ASSISTANT_SPEC,)


class FakeModelFactory:
    model: ClassVar[Model] = text_model("Hello")

    def build(self, *, role: ModelRole, user_id: UserId) -> Model:
        return type(self).model


class FakeTransport:
    events: ClassVar[list[tuple[str, TurnEventDTO]]] = []

    @classmethod
    def reset(cls) -> None:
        cls.events = []

    def publish(self, *, turn_id: str, event: TurnEventDTO) -> str:
        type(self).events.append((turn_id, event))
        return str(len(type(self).events))

    async def read(
        self,
        *,
        turn_id: str,
        after_id: str = START_EVENT_ID,
    ) -> AsyncGenerator[StreamedTurnEventDTO | None]:
        """Yield the stored events of the turn after after_id, then stop."""
        for number, (event_turn_id, event) in enumerate(type(self).events, start=1):
            if event_turn_id == turn_id and number > int(after_id):
                yield StreamedTurnEventDTO(event_id=str(number), event=event)


class FakeTaskRunner:
    turn_ids: ClassVar[list[str]] = []

    @classmethod
    def reset(cls) -> None:
        cls.turn_ids = []

    def enqueue(self, *, turn_id: str) -> None:
        type(self).turn_ids.append(turn_id)


class AllowAll:
    def can_use(self, *, user_id: UserId, agent_name: str) -> bool:
        return True
