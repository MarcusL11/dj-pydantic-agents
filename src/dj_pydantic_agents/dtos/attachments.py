"""The commands, queries and projections of the files of a message."""

from typing import Annotated

from pydantic import Field
from pydantic import StringConstraints

from dj_pydantic_agents.dtos.shared_types import UserId  # noqa: TC001
from dj_pydantic_agents.kit.dtos import InternalDTO

# The name of a file as the transcript and the model see it: one line.
type FileName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]


class UploadedFileDTO(InternalDTO):
    """One file of an upload request, before the checks."""

    name: str
    data: bytes


class UploadAttachmentsCommandDTO(InternalDTO):
    conversation_id: str
    user_id: UserId
    files: tuple[UploadedFileDTO, ...] = Field(min_length=1)


class NewAttachmentDTO(InternalDTO):
    """A checked file in storage, ready for its row."""

    attachment_id: str
    path: str
    name: FileName
    media_type: str
    size: int = Field(ge=1)
    sha256: str = Field(min_length=64, max_length=64)


class AddPendingAttachmentsCommandDTO(InternalDTO):
    """Add the rows. Refuse them all if the pending files go over a limit."""

    conversation_id: str
    user_id: UserId
    attachments: tuple[NewAttachmentDTO, ...] = Field(min_length=1)
    max_files: int = Field(ge=1)
    max_bytes: int = Field(ge=1)
    pending_seconds: int = Field(gt=0)


class RemoveAttachmentCommandDTO(InternalDTO):
    attachment_id: str
    user_id: UserId


class AttachmentRemovedResultDTO(InternalDTO):
    """The file goes after the commit. The page shows the rest of the pending files."""

    conversation_id: str
    path: str


class DeleteExpiredAttachmentsCommandDTO(InternalDTO):
    pending_seconds: int = Field(gt=0)


class AttachmentFilesResultDTO(InternalDTO):
    """The stored paths of deleted rows. Their files go after the commit."""

    paths: tuple[str, ...] = ()


class AttachmentProjectionDTO(InternalDTO):
    """A file as the page shows it, as a chip with a link."""

    attachment_id: str
    name: str
    media_type: str
    size: int
    is_image: bool


class PendingAttachmentsProjectionDTO(InternalDTO):
    """The pending files of the user in the conversation, oldest first."""

    conversation_id: str
    attachments: tuple[AttachmentProjectionDTO, ...]


class GetPendingAttachmentsQueryDTO(InternalDTO):
    conversation_id: str
    user_id: UserId
    pending_seconds: int = Field(gt=0)


class GetAttachmentFileQueryDTO(InternalDTO):
    attachment_id: str
    user_id: UserId


class AttachmentFileProjectionDTO(InternalDTO):
    """Where a file is. Only the owner of its conversation gets it."""

    agent_name: str
    path: str
    name: str
    media_type: str


class AttachmentContentDTO(InternalDTO):
    """The bytes of a file, for a download."""

    name: str
    media_type: str
    data: bytes


class RunAttachmentDTO(InternalDTO):
    """A file of one of the latest turns. The run reads its bytes."""

    attachment_id: str
    turn_id: str
    path: str
    name: str
    media_type: str
