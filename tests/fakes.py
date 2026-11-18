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
from dj_pydantic_agents.kit.attachments import FileRefDTO
from dj_pydantic_agents.kit.attachments import PromptFile
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


class FakePromptFiles:
    """PROMPT_FILES with files in memory. A test sets the class values."""

    pending_files: ClassVar[tuple[FileRefDTO, ...]] = ()
    described: ClassVar[tuple[FileRefDTO, ...]] = ()
    files: ClassVar[tuple[PromptFile, ...]] = ()
    # An error that claim() raises, for example FilesRefused.
    refusal: ClassVar[Exception | None] = None
    claims: ClassVar[list[dict[str, object]]] = []
    loads: ClassVar[list[tuple[str, ...]]] = []
    forgotten: ClassVar[list[str]] = []

    @classmethod
    def reset(cls) -> None:
        cls.pending_files = cls.described = ()
        cls.files = ()
        cls.refusal = None
        cls.claims = []
        cls.loads = []
        cls.forgotten = []

    def pending(
        self,
        *,
        conversation_id: str,
        user_id: UserId,
    ) -> tuple[FileRefDTO, ...]:
        return type(self).pending_files

    def claim(
        self,
        *,
        conversation_id: str,
        user_id: UserId,
        turn_id: str,
        file_ids: tuple[str, ...],
    ) -> tuple[FileRefDTO, ...]:
        type(self).claims.append(
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "turn_id": turn_id,
                "file_ids": file_ids,
            },
        )
        if (refusal := type(self).refusal) is not None:
            raise refusal
        return tuple(
            FileRefDTO(
                file_id=file_id,
                name=f"{file_id}.pdf",
                media_type="application/pdf",
            )
            for file_id in file_ids
        )

    def describe(self, *, file_ids: tuple[str, ...]) -> tuple[FileRefDTO, ...]:
        return tuple(file for file in type(self).described if file.file_id in file_ids)

    def load(self, *, turn_ids: tuple[str, ...]) -> tuple[PromptFile, ...]:
        type(self).loads.append(turn_ids)
        return tuple(file for file in type(self).files if file.turn_id in turn_ids)

    def forget(self, *, conversation_id: str) -> None:
        type(self).forgotten.append(conversation_id)
