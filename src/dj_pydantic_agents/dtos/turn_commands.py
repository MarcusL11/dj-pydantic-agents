"""The commands and results of conversations, turns and approvals."""

from typing import Annotated
from typing import Any
from typing import Literal
from typing import Self

from pydantic import Field
from pydantic import StringConstraints
from pydantic import model_validator

from dj_pydantic_agents.dtos.attachments import AttachmentProjectionDTO  # noqa: TC001
from dj_pydantic_agents.dtos.attachments import RunAttachmentDTO  # noqa: TC001
from dj_pydantic_agents.dtos.shared_types import MessageJson
from dj_pydantic_agents.dtos.shared_types import UserId
from dj_pydantic_agents.kit.dtos import InternalDTO
from dj_pydantic_agents.kit.events import PendingApprovalDTO  # noqa: TC001

__all__ = ["MessageJson", "UserId"]


class CreateConversationCommandDTO(InternalDTO):
    owner_id: UserId
    agent_name: str = Field(min_length=1, max_length=100)
    title: str = Field(default="", max_length=200)


class ConversationCreatedResultDTO(InternalDTO):
    conversation_id: str


class RenameConversationCommandDTO(InternalDTO):
    """The title loses its outer spaces. A title of only spaces is refused."""

    conversation_id: str
    user_id: UserId
    title: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    ]


class DeleteConversationCommandDTO(InternalDTO):
    conversation_id: str
    user_id: UserId


class ConversationDeletedResultDTO(InternalDTO):
    """The stored paths of the files of the conversation. They go after the commit."""

    attachment_paths: tuple[str, ...] = ()


class StartTurnCommandDTO(InternalDTO):
    """The message takes the pending files of attachment_ids."""

    conversation_id: str
    user_id: UserId
    prompt: str = Field(min_length=1)
    attachment_ids: tuple[str, ...] = ()


class TurnStartedResultDTO(InternalDTO):
    turn_id: str
    conversation_id: str
    attachments: tuple[AttachmentProjectionDTO, ...] = ()


class ClaimTurnCommandDTO(InternalDTO):
    turn_id: str
    # The run gets the files of this number of latest turns, with this turn.
    history_turns: int = Field(default=2, ge=1)


class TurnRunInputDTO(InternalDTO):
    """All that one run of a turn needs.

    A first run has a prompt. A resume has the pending approvals and the
    decisions, and no prompt.
    """

    turn_id: str
    conversation_id: str
    agent_name: str
    user_id: UserId
    history: tuple[MessageJson, ...]
    prompt: str | None
    pending: dict[str, Any] | None
    # Each decided approval of the turn, by tool call ID. After a second stop,
    # this also holds the decisions of the first stop.
    decisions: dict[str, bool] | None
    # The files of the latest turns, this turn included.
    attachments: tuple[RunAttachmentDTO, ...] = ()


class TurnUsageDTO(InternalDTO):
    requests: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    output_reasoning_tokens: int = Field(default=0, ge=0)


class SaveTurnResultCommandDTO(InternalDTO):
    """The result of one run. Approvals make the turn wait for decisions."""

    turn_id: str
    new_messages: tuple[MessageJson, ...]
    pending: dict[str, Any] | None
    approvals: tuple[PendingApprovalDTO, ...]
    usage: TurnUsageDTO

    @model_validator(mode="after")
    def _approvals_match_pending(self) -> Self:
        if (self.pending is None) != (not self.approvals):
            msg = "Give the pending requests and their approvals together."
            raise ValueError(msg)
        return self


class TurnSavedResultDTO(InternalDTO):
    turn_id: str
    status: Literal["waiting_approval", "done"]


class FailTurnCommandDTO(InternalDTO):
    turn_id: str
    error_code: str = Field(min_length=1, max_length=50)


class FailStaleTurnCommandDTO(InternalDTO):
    turn_id: str
    stale_seconds: int = Field(gt=0)
    error_code: str = Field(min_length=1, max_length=50)


class DecideApprovalCommandDTO(InternalDTO):
    approval_id: str
    user_id: UserId
    approved: bool


class ApprovalDecidedResultDTO(InternalDTO):
    """requeued is True when this was the last pending decision of the turn."""

    approval_id: str
    turn_id: str
    conversation_id: str
    requeued: bool


class RunTurnCommandDTO(InternalDTO):
    turn_id: str
