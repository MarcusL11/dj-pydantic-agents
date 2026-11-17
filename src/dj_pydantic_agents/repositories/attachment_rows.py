"""The attachment reads that more than one repository uses."""

from typing import TYPE_CHECKING
from typing import Any

from dj_pydantic_agents.dtos.attachments import AttachmentProjectionDTO
from dj_pydantic_agents.models import Attachment

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from dj_pydantic_agents.dtos.shared_types import UserId

PROJECTION_FIELDS = ("id", "name", "media_type", "size")


def pending_attachments(
    *,
    conversation_id: str,
    user_id: UserId,
    since: datetime,
) -> tuple[AttachmentProjectionDTO, ...]:
    """The pending files of the user that are not expired, oldest first."""
    return tuple(
        attachment_projection(row)
        for row in Attachment.objects.filter(
            conversation_id=conversation_id,
            uploaded_by_id=user_id,  # type: ignore[misc]
            turn__isnull=True,
            created_at__gte=since,
        )
        .order_by("created_at", "id")
        .values(*PROJECTION_FIELDS)
    )


def attachment_projection(row: Mapping[str, Any]) -> AttachmentProjectionDTO:
    return AttachmentProjectionDTO(
        attachment_id=row["id"],
        name=row["name"],
        media_type=row["media_type"],
        size=row["size"],
        is_image=row["media_type"].startswith("image/"),
    )
