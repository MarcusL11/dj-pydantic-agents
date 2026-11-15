"""Hooks for projects, for example to write an audit row.

The package sends these signals and holds no receiver of its own.
"""

import logging
from typing import TYPE_CHECKING

from django.dispatch import Signal

if TYPE_CHECKING:
    from dj_pydantic_agents.kit.dtos import InternalDTO

logger = logging.getLogger(__name__)

# Sent after each run of a turn, with event=TurnFinishedEventDTO.
turn_finished = Signal()

# Sent after each approval decision, with event=ApprovalDecidedEventDTO.
approval_decided = Signal()


def send_hook(signal: Signal, *, sender: type, event: InternalDTO) -> None:
    """Send the signal. Log a receiver error, so that it cannot stop a turn."""
    for receiver, response in signal.send_robust(sender=sender, event=event):
        if isinstance(response, Exception):
            logger.error(
                "A %s receiver failed: %r",
                type(event).__name__,
                receiver,
                exc_info=response,
            )
