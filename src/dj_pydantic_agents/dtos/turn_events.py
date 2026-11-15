"""The payloads of the turn_finished and approval_decided signals."""

from typing import Literal

from dj_pydantic_agents.dtos.turn_commands import UserId  # noqa: TC001
from dj_pydantic_agents.kit.dtos import InternalDTO

type TurnRunStatus = Literal["waiting_approval", "done", "failed"]


class TurnFinishedEventDTO(InternalDTO):
    """One run of a turn stopped: with a reply, for approval, or with an error."""

    turn_id: str
    conversation_id: str
    agent_name: str
    user_id: UserId
    status: TurnRunStatus
    error_code: str


class ApprovalDecidedEventDTO(InternalDTO):
    approval_id: str
    turn_id: str
    user_id: UserId
    approved: bool
