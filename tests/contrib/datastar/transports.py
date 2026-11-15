"""Event transports for the stream view tests."""

import asyncio
from collections.abc import AsyncGenerator  # noqa: TC003
from typing import ClassVar

from dj_pydantic_agents.kit.events import START_EVENT_ID
from dj_pydantic_agents.kit.events import StreamedTurnEventDTO
from dj_pydantic_agents.kit.events import TurnEventDTO
from tests.fakes import FakeTransport

WAIT_SECONDS = 3600


class ScriptedTransport(FakeTransport):
    """Yield the stored events like the Redis transport: stop after a final event.

    A None in the script is a wait with no event. After the script, the read
    waits until the stream stops it. The reads record their after_id and
    their close.
    """

    script: ClassVar[list[TurnEventDTO | None]] = []
    reads: ClassVar[list[str]] = []
    closed: ClassVar[int] = 0

    @classmethod
    def reset(cls) -> None:
        cls.script = []
        cls.reads = []
        cls.closed = 0

    async def read(
        self,
        *,
        turn_id: str,
        after_id: str = START_EVENT_ID,
    ) -> AsyncGenerator[StreamedTurnEventDTO | None]:
        cls = type(self)
        cls.reads.append(after_id)
        try:
            for number, event in enumerate(cls.script, start=1):
                if number <= int(after_id):
                    continue
                if event is None:
                    yield None
                    continue
                streamed = StreamedTurnEventDTO(event_id=str(number), event=event)
                yield streamed
                if streamed.is_final:
                    return
            await asyncio.sleep(WAIT_SECONDS)
        finally:
            cls.closed += 1
