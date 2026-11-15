"""Combine the text events of a run, so that a page gets fewer patches."""

import time
from typing import TYPE_CHECKING

from dj_pydantic_agents.kit.events import TextDeltaEventDTO

if TYPE_CHECKING:
    from collections.abc import Callable

    from dj_pydantic_agents.kit.events import TurnEventDTO
    from dj_pydantic_agents.kit.runner import EventSink

# The shortest time between two text events.
TEXT_INTERVAL_SECONDS = 0.075


class TextCombiner:
    """Publish at most one text event each TEXT_INTERVAL_SECONDS.

    A text that comes too soon waits, and the next text adds to it. Each other
    event publishes the waiting text first, so the order stays correct. Call
    flush() at the end of the run.
    """

    def __init__(
        self,
        publish: EventSink,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._publish = publish
        self._clock = clock
        self._waiting: list[str] = []
        self._published_at: float | None = None

    def __call__(self, event: TurnEventDTO) -> None:
        if not isinstance(event, TextDeltaEventDTO):
            self.flush()
            self._publish(event)
            return
        self._waiting.append(event.text)
        now = self._clock()
        if (
            self._published_at is None
            or now - self._published_at >= TEXT_INTERVAL_SECONDS
        ):
            self._publish_text(now=now)

    def flush(self) -> None:
        """Publish the waiting text."""
        if self._waiting:
            self._publish_text(now=self._clock())

    def _publish_text(self, *, now: float) -> None:
        text = "".join(self._waiting)
        self._waiting = []
        self._published_at = now
        self._publish(TextDeltaEventDTO(text=text))
