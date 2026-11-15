"""The queries and the projections of the conversation pages."""

from datetime import datetime  # noqa: TC003
from typing import Literal

from dj_pydantic_agents.dtos.turn_commands import UserId  # noqa: TC001
from dj_pydantic_agents.kit.dtos import InternalDTO
from dj_pydantic_agents.kit.transcript import TranscriptLineDTO  # noqa: TC001


class GetConversationPageQueryDTO(InternalDTO):
    conversation_id: str
    user_id: UserId


type ActiveTurnStatus = Literal["queued", "running", "waiting_approval"]


class ActiveTurnProjectionDTO(InternalDTO):
    """unsaved_prompt is the prompt of a first run, before its messages are saved."""

    turn_id: str
    status: ActiveTurnStatus
    unsaved_prompt: str | None


class ApprovalProjectionDTO(InternalDTO):
    """A tool call of the active turn that waits for a decision."""

    approval_id: str
    tool_name: str
    args_json: str


class ConversationPageProjectionDTO(InternalDTO):
    conversation_id: str
    agent_name: str
    title: str
    lines: tuple[TranscriptLineDTO, ...]
    active_turn: ActiveTurnProjectionDTO | None
    approvals: tuple[ApprovalProjectionDTO, ...]


class GetConversationAgentQueryDTO(InternalDTO):
    conversation_id: str
    user_id: UserId


class GetTurnAgentQueryDTO(InternalDTO):
    turn_id: str
    user_id: UserId


class GetApprovalAgentQueryDTO(InternalDTO):
    approval_id: str
    user_id: UserId


class AgentNameProjectionDTO(InternalDTO):
    agent_name: str


class ListConversationsQueryDTO(InternalDTO):
    user_id: UserId
    agent_name: str


class ConversationSummaryProjectionDTO(InternalDTO):
    """One line of a conversation list. The title is empty before the first message."""

    conversation_id: str
    title: str
    updated_at: datetime
    active_turn_status: ActiveTurnStatus | None
