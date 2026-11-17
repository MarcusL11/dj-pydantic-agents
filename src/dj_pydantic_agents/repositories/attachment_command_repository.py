"""Complete atomic mutations of the pending files of a message."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.db.models import Sum
from django.utils import timezone

from dj_pydantic_agents.dtos.attachments import AddPendingAttachmentsCommandDTO
from dj_pydantic_agents.dtos.attachments import AttachmentFilesResultDTO
from dj_pydantic_agents.dtos.attachments import AttachmentRemovedResultDTO
from dj_pydantic_agents.dtos.attachments import DeleteExpiredAttachmentsCommandDTO
from dj_pydantic_agents.dtos.attachments import PendingAttachmentsProjectionDTO
from dj_pydantic_agents.dtos.attachments import RemoveAttachmentCommandDTO
from dj_pydantic_agents.errors import AttachmentNotPending
from dj_pydantic_agents.errors import AttachmentRefused
from dj_pydantic_agents.errors import ConversationNotFound
from dj_pydantic_agents.models import Attachment
from dj_pydantic_agents.models import Conversation
from dj_pydantic_agents.repositories.attachment_rows import pending_attachments


class AttachmentCommandRepository:
    """Add, remove and expire pending files.

    The send of a message takes them, in TurnCommandRepository.start_turn().
    """

    @transaction.atomic
    def add_pending(
        self,
        *,
        command: AddPendingAttachmentsCommandDTO,
    ) -> PendingAttachmentsProjectionDTO:
        """Add the rows. Refuse all of them if the pending files go over a limit.

        The lock on the conversation row makes two uploads count one at a time.
        """
        conversation_id = (
            Conversation.objects.select_for_update()  # type: ignore[misc]
            .filter(id=command.conversation_id, owner_id=command.user_id)
            .values_list("id", flat=True)
            .first()
        )
        if conversation_id is None:
            msg = "The conversation was not found."
            raise ConversationNotFound(msg)

        since = timezone.now() - timedelta(seconds=command.pending_seconds)
        pending = Attachment.objects.filter(
            conversation_id=conversation_id,
            uploaded_by_id=command.user_id,  # type: ignore[misc]
            turn__isnull=True,
            created_at__gte=since,
        ).aggregate(files=Count("id"), size=Sum("size", default=0))
        new_size = sum(attachment.size for attachment in command.attachments)
        if pending["files"] + len(command.attachments) > command.max_files:
            msg = f"A message can have {command.max_files} files at most."
            raise AttachmentRefused(msg)
        if pending["size"] + new_size > command.max_bytes:
            megabytes = command.max_bytes // (1024 * 1024)
            msg = f"The files of a message can have {megabytes} MB at most."
            raise AttachmentRefused(msg)

        Attachment.objects.bulk_create(
            Attachment(
                id=attachment.attachment_id,
                conversation_id=conversation_id,
                uploaded_by_id=command.user_id,  # type: ignore[misc]
                file=attachment.path,
                name=attachment.name,
                media_type=attachment.media_type,
                size=attachment.size,
                sha256=attachment.sha256,
            )
            for attachment in command.attachments
        )
        return PendingAttachmentsProjectionDTO(
            conversation_id=conversation_id,
            attachments=pending_attachments(
                conversation_id=conversation_id,
                user_id=command.user_id,
                since=since,
            ),
        )

    @transaction.atomic
    def remove_pending(
        self,
        *,
        command: RemoveAttachmentCommandDTO,
    ) -> AttachmentRemovedResultDTO:
        """Delete a pending file of the user. A sent file stays."""
        row = (
            Attachment.objects.select_for_update()
            .filter(
                id=command.attachment_id,
                uploaded_by_id=command.user_id,  # type: ignore[misc]
                conversation__owner_id=command.user_id,
                turn__isnull=True,
            )
            .values("id", "conversation_id", "file")
            .first()
        )
        if row is None:
            msg = "The file is not pending."
            raise AttachmentNotPending(msg)
        Attachment.objects.filter(id=row["id"]).delete()
        return AttachmentRemovedResultDTO(
            conversation_id=row["conversation_id"],
            path=row["file"],
        )

    @transaction.atomic
    def delete_expired(
        self,
        *,
        command: DeleteExpiredAttachmentsCommandDTO,
    ) -> AttachmentFilesResultDTO:
        """Delete the pending files older than pending_seconds.

        SKIP LOCKED leaves a row that a send locks now. That send refuses an
        expired row, and the next cleanup deletes it.
        """
        since = timezone.now() - timedelta(seconds=command.pending_seconds)
        rows = list(
            Attachment.objects.select_for_update(skip_locked=True)
            .filter(turn__isnull=True, created_at__lt=since)
            .values_list("id", "file"),
        )
        Attachment.objects.filter(id__in=[row_id for row_id, _ in rows]).delete()
        return AttachmentFilesResultDTO(paths=tuple(path for _, path in rows))
