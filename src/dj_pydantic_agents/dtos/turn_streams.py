"""The command and the snapshot of a turn stream."""

from typing import Literal

from dj_pydantic_agents.dtos.conversation_queries import (
    ApprovalProjectionDTO,  # noqa: TC001
)
from dj_pydantic_agents.dtos.turn_commands import UserId  # noqa: TC001
from dj_pydantic_agents.kit.dtos import InternalDTO

type TurnStatusName = Literal["queued", "running", "waiting_approval", "done", "failed"]

# A worker runs a turn in these states, so the stream reads its events.
STREAMING_STATUSES = frozenset({"queued", "running"})


class OpenTurnStreamCommandDTO(InternalDTO):
    turn_id: str
    user_id: UserId


class GetTurnSnapshotQueryDTO(InternalDTO):
    turn_id: str
    user_id: UserId


class TurnSnapshotProjectionDTO(InternalDTO):
    """The state of a turn when a stream opens.

    reply_text is the text of the last model response, for a done or a waiting
    turn. approvals holds the pending approvals of a waiting turn. While a
    worker runs the turn, decided_tool_call_ids holds the tool calls of its
    earlier stops, so that the stream can skip their events.
    """

    turn_id: str
    conversation_id: str
    status: TurnStatusName
    reply_text: str
    error_code: str
    approvals: tuple[ApprovalProjectionDTO, ...]
    decided_tool_call_ids: tuple[str, ...]

    @property
    def is_streaming(self) -> bool:
        return self.status in STREAMING_STATUSES
