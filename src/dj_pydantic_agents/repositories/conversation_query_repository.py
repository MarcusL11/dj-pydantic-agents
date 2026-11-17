"""Read the conversation pages."""

from datetime import timedelta
from typing import TYPE_CHECKING
from typing import cast

from django.db.models import OuterRef
from django.db.models import Subquery
from django.utils import timezone

from dj_pydantic_agents.dtos.attachments import AttachmentFileProjectionDTO
from dj_pydantic_agents.dtos.attachments import AttachmentProjectionDTO
from dj_pydantic_agents.dtos.attachments import GetAttachmentFileQueryDTO
from dj_pydantic_agents.dtos.attachments import GetPendingAttachmentsQueryDTO
from dj_pydantic_agents.dtos.attachments import PendingAttachmentsProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import ActiveTurnProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import ActiveTurnStatus
from dj_pydantic_agents.dtos.conversation_queries import AgentNameProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import ApprovalProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import ConversationPageProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import (
    ConversationSummaryProjectionDTO,
)
from dj_pydantic_agents.dtos.conversation_queries import GetApprovalAgentQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import GetConversationAgentQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import GetConversationPageQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import GetTurnAgentQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import ListConversationsQueryDTO
from dj_pydantic_agents.dtos.turn_streams import GetTurnSnapshotQueryDTO
from dj_pydantic_agents.dtos.turn_streams import TurnSnapshotProjectionDTO
from dj_pydantic_agents.dtos.turn_streams import TurnStatusName
from dj_pydantic_agents.errors import ApprovalNotPending
from dj_pydantic_agents.errors import AttachmentNotFound
from dj_pydantic_agents.errors import ConversationNotFound
from dj_pydantic_agents.kit.history import messages_from_json
from dj_pydantic_agents.kit.transcript import TranscriptLineDTO
from dj_pydantic_agents.kit.transcript import last_reply_text
from dj_pydantic_agents.kit.transcript import transcript_lines
from dj_pydantic_agents.models import ACTIVE_TURN_STATUSES
from dj_pydantic_agents.models import Attachment
from dj_pydantic_agents.models import Conversation
from dj_pydantic_agents.models import PendingApproval
from dj_pydantic_agents.models import Turn
from dj_pydantic_agents.repositories.attachment_rows import PROJECTION_FIELDS
from dj_pydantic_agents.repositories.attachment_rows import attachment_projection
from dj_pydantic_agents.repositories.attachment_rows import pending_attachments

if TYPE_CHECKING:
    from dj_pydantic_agents.kit.attachments import PromptFileRefDTO


class ConversationQueryRepository:
    def list_conversations(
        self,
        *,
        query: ListConversationsQueryDTO,
    ) -> tuple[ConversationSummaryProjectionDTO, ...]:
        """The conversations of the user with the agent, newest first."""
        active_status = Turn.objects.filter(
            conversation_id=OuterRef("id"),
            status__in=ACTIVE_TURN_STATUSES,
        ).values("status")[:1]
        rows = (
            Conversation.objects.filter(
                owner_id=query.user_id,  # type: ignore[misc]
                agent_name=query.agent_name,
            )
            .annotate(active_turn_status=Subquery(active_status))
            .order_by("-updated_at", "-id")
            .values("id", "title", "updated_at", "active_turn_status")
        )
        return tuple(
            ConversationSummaryProjectionDTO(
                conversation_id=row["id"],
                title=row["title"],
                updated_at=row["updated_at"],
                active_turn_status=row["active_turn_status"],
            )
            for row in rows
        )

    def get_conversation_agent(
        self,
        *,
        query: GetConversationAgentQueryDTO,
    ) -> AgentNameProjectionDTO:
        agent_name = (
            Conversation.objects.filter(
                id=query.conversation_id,
                owner_id=query.user_id,  # type: ignore[misc]
            )
            .values_list("agent_name", flat=True)
            .first()
        )
        if agent_name is None:
            msg = "The conversation was not found."
            raise ConversationNotFound(msg)
        return AgentNameProjectionDTO(agent_name=agent_name)

    def get_approval_agent(
        self,
        *,
        query: GetApprovalAgentQueryDTO,
    ) -> AgentNameProjectionDTO:
        agent_name = (
            PendingApproval.objects.filter(
                id=query.approval_id,
                turn__conversation__owner_id=query.user_id,  # type: ignore[misc]
            )
            .values_list("turn__conversation__agent_name", flat=True)
            .first()
        )
        if agent_name is None:
            msg = "The approval does not wait for a decision."
            raise ApprovalNotPending(msg)
        return AgentNameProjectionDTO(agent_name=agent_name)

    def get_turn_agent(self, *, query: GetTurnAgentQueryDTO) -> AgentNameProjectionDTO:
        agent_name = (
            Turn.objects.filter(
                id=query.turn_id,
                conversation__owner_id=query.user_id,  # type: ignore[misc]
            )
            .values_list("conversation__agent_name", flat=True)
            .first()
        )
        if agent_name is None:
            msg = "The turn was not found."
            raise ConversationNotFound(msg)
        return AgentNameProjectionDTO(agent_name=agent_name)

    def get_turn_snapshot(
        self,
        *,
        query: GetTurnSnapshotQueryDTO,
    ) -> TurnSnapshotProjectionDTO:
        """Read only the parts that the status of the turn needs."""
        turn = (
            Turn.objects.filter(
                id=query.turn_id,
                conversation__owner_id=query.user_id,  # type: ignore[misc]
            )
            .values("id", "conversation_id", "status", "error_code")
            .first()
        )
        if turn is None:
            msg = "The turn was not found."
            raise ConversationNotFound(msg)

        status = cast("TurnStatusName", turn["status"])
        reply_text = ""
        if status in {Turn.Status.DONE, Turn.Status.WAITING_APPROVAL}:
            reply_text = _last_reply_text(conversation_id=turn["conversation_id"])
        streaming = status in {Turn.Status.QUEUED, Turn.Status.RUNNING}
        return TurnSnapshotProjectionDTO(
            turn_id=turn["id"],
            conversation_id=turn["conversation_id"],
            status=status,
            reply_text=reply_text,
            error_code=turn["error_code"],
            approvals=_pending_approvals(turn_id=turn["id"])
            if status == Turn.Status.WAITING_APPROVAL
            else (),
            decided_tool_call_ids=_decided_tool_call_ids(turn_id=turn["id"])
            if streaming
            else (),
        )

    def get_pending_attachments(
        self,
        *,
        query: GetPendingAttachmentsQueryDTO,
    ) -> PendingAttachmentsProjectionDTO:
        """The files that wait for the next message, oldest first."""
        return PendingAttachmentsProjectionDTO(
            conversation_id=query.conversation_id,
            attachments=pending_attachments(
                conversation_id=query.conversation_id,
                user_id=query.user_id,
                since=timezone.now() - timedelta(seconds=query.pending_seconds),
            ),
        )

    def get_attachment_file(
        self,
        *,
        query: GetAttachmentFileQueryDTO,
    ) -> AttachmentFileProjectionDTO:
        """Only the owner of the conversation gets the file."""
        row = (
            Attachment.objects.filter(
                id=query.attachment_id,
                conversation__owner_id=query.user_id,  # type: ignore[misc]
            )
            .values("conversation__agent_name", "file", "name", "media_type")
            .first()
        )
        if row is None:
            msg = "The file was not found."
            raise AttachmentNotFound(msg)
        return AttachmentFileProjectionDTO(
            agent_name=row["conversation__agent_name"],
            path=row["file"],
            name=row["name"],
            media_type=row["media_type"],
        )

    def get_conversation_page(
        self,
        *,
        query: GetConversationPageQueryDTO,
    ) -> ConversationPageProjectionDTO:
        conversation = (
            Conversation.objects.filter(  # type: ignore[misc]
                id=query.conversation_id,
                owner_id=query.user_id,
            )
            .values("id", "agent_name", "title", "messages", "pending_approvals")
            .first()
        )
        if conversation is None:
            msg = "The conversation was not found."
            raise ConversationNotFound(msg)

        turn = (
            Turn.objects.filter(
                conversation_id=conversation["id"],
                status__in=ACTIVE_TURN_STATUSES,
            )
            .values("id", "status", "prompt")
            .first()
        )
        active_turn = None
        approvals: tuple[ApprovalProjectionDTO, ...] = ()
        if turn is not None:
            # A first run saves its messages at the end. Until then, only the
            # turn holds the prompt.
            first_run = conversation["pending_approvals"] is None
            active_turn = ActiveTurnProjectionDTO(
                turn_id=turn["id"],
                status=cast("ActiveTurnStatus", turn["status"]),
                unsaved_prompt=turn["prompt"] if first_run else None,
                unsaved_files=_turn_attachments(turn_id=turn["id"])
                if first_run
                else (),
            )
            approvals = _pending_approvals(turn_id=turn["id"])

        return ConversationPageProjectionDTO(
            conversation_id=conversation["id"],
            agent_name=conversation["agent_name"],
            title=conversation["title"],
            lines=_with_file_sizes(
                conversation_id=conversation["id"],
                lines=transcript_lines(messages_from_json(conversation["messages"])),
            ),
            active_turn=active_turn,
            approvals=approvals,
        )


def _with_file_sizes(
    *,
    conversation_id: str,
    lines: tuple[TranscriptLineDTO, ...],
) -> tuple[TranscriptLineDTO, ...]:
    """The rows give the sizes. A transcript with no file needs no query."""
    if not any(line.files for line in lines):
        return lines
    sizes = dict(
        Attachment.objects.filter(
            conversation_id=conversation_id,
            turn__isnull=False,
        ).values_list("id", "size"),
    )
    return tuple(
        line.model_copy(
            update={"files": tuple(_sized(file, sizes) for file in line.files)},
        )
        if line.files
        else line
        for line in lines
    )


def _sized(file: PromptFileRefDTO, sizes: dict[str, int]) -> PromptFileRefDTO:
    return file.model_copy(update={"size": sizes.get(file.attachment_id)})


def _turn_attachments(*, turn_id: str) -> tuple[AttachmentProjectionDTO, ...]:
    return tuple(
        attachment_projection(row)
        for row in Attachment.objects.filter(turn_id=turn_id)
        .order_by("created_at", "id")
        .values(*PROJECTION_FIELDS)
    )


def _pending_approvals(*, turn_id: str) -> tuple[ApprovalProjectionDTO, ...]:
    return tuple(
        ApprovalProjectionDTO(
            approval_id=approval["id"],
            tool_name=approval["tool_name"],
            args_json=approval["args_json"],
        )
        for approval in PendingApproval.objects.filter(
            turn_id=turn_id,
            decision=PendingApproval.Decision.PENDING,
        )
        .order_by("id")
        .values("id", "tool_name", "args_json")
    )


def _last_reply_text(*, conversation_id: str) -> str:
    messages = Conversation.objects.values_list("messages", flat=True).get(
        id=conversation_id,
    )
    return last_reply_text(messages_from_json(messages))


def _decided_tool_call_ids(*, turn_id: str) -> tuple[str, ...]:
    return tuple(
        PendingApproval.objects.filter(turn_id=turn_id)
        .exclude(decision=PendingApproval.Decision.PENDING)
        .order_by("id")
        .values_list("tool_call_id", flat=True),
    )
