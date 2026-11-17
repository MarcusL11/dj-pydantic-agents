"""Upload, remove and expire the files of the next message."""

# create_autospec() reads the annotations of each method, so the annotation
# types load at runtime.
# ruff: noqa: TC001, TC003

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

from dj_pydantic_agents.dtos.attachments import AddPendingAttachmentsCommandDTO
from dj_pydantic_agents.dtos.attachments import DeleteExpiredAttachmentsCommandDTO
from dj_pydantic_agents.dtos.attachments import GetPendingAttachmentsQueryDTO
from dj_pydantic_agents.dtos.attachments import NewAttachmentDTO
from dj_pydantic_agents.dtos.attachments import PendingAttachmentsProjectionDTO
from dj_pydantic_agents.dtos.attachments import RemoveAttachmentCommandDTO
from dj_pydantic_agents.dtos.attachments import UploadAttachmentsCommandDTO
from dj_pydantic_agents.dtos.attachments import UploadedFileDTO
from dj_pydantic_agents.dtos.conversation_queries import GetConversationAgentQueryDTO
from dj_pydantic_agents.dtos.shared_types import UserId
from dj_pydantic_agents.errors import AgentAccessDenied
from dj_pydantic_agents.errors import AgentNotFound
from dj_pydantic_agents.errors import AttachmentRefused
from dj_pydantic_agents.extensions import AgentPermission
from dj_pydantic_agents.files import AttachmentFileStore
from dj_pydantic_agents.ids import new_attachment_id
from dj_pydantic_agents.kit.file_checks import SUFFIXES
from dj_pydantic_agents.kit.file_checks import FileCheckError
from dj_pydantic_agents.kit.file_checks import media_type_of
from dj_pydantic_agents.kit.file_checks import shrink_image
from dj_pydantic_agents.kit.specs import AgentSpec
from dj_pydantic_agents.repositories.attachment_command_repository import (
    AttachmentCommandRepository,
)
from dj_pydantic_agents.repositories.conversation_query_repository import (
    ConversationQueryRepository,
)

# The folder of the stored files in the storage.
STORAGE_FOLDER = "dj_pydantic_agents/attachments"
NAME_LENGTH = 255


@dataclass(frozen=True, kw_only=True)
class AttachmentRules:
    """The project values of the ATTACHMENT_* settings."""

    media_types: tuple[str, ...]
    max_files: int
    max_file_bytes: int
    max_message_bytes: int
    pending_seconds: int


class AttachmentCommandService:
    def __init__(  # noqa: PLR0913
        self,
        *,
        repository: AttachmentCommandRepository,
        queries: ConversationQueryRepository,
        files: AttachmentFileStore,
        specs: Mapping[str, AgentSpec],
        permission: AgentPermission,
        rules: AttachmentRules,
    ) -> None:
        self._repository = repository
        self._queries = queries
        self._files = files
        self._specs = specs
        self._permission = permission
        self._rules = rules

    def upload_attachments(
        self,
        *,
        command: UploadAttachmentsCommandDTO,
    ) -> PendingAttachmentsProjectionDTO:
        """Check and store the files. Then they wait for the next message.

        A file that fails a check refuses the full upload, and nothing is stored.
        """
        self._check_conversation_access(
            conversation_id=command.conversation_id,
            user_id=command.user_id,
        )
        if not self._rules.media_types:
            msg = "This chat takes no files."
            raise AttachmentRefused(msg)
        if len(command.files) > self._rules.max_files:
            msg = f"A message can have {self._rules.max_files} files at most."
            raise AttachmentRefused(msg)
        attachments = tuple(
            self._checked(file=file, conversation_id=command.conversation_id)
            for file in command.files
        )
        stored: list[NewAttachmentDTO] = []
        try:
            for attachment, data in attachments:
                path = self._files.save(path=attachment.path, data=data)
                stored.append(attachment.model_copy(update={"path": path}))
            return self._repository.add_pending(
                command=AddPendingAttachmentsCommandDTO(
                    conversation_id=command.conversation_id,
                    user_id=command.user_id,
                    attachments=tuple(stored),
                    max_files=self._rules.max_files,
                    max_bytes=self._rules.max_message_bytes,
                    pending_seconds=self._rules.pending_seconds,
                ),
            )
        except Exception:
            self._files.delete(paths=tuple(attachment.path for attachment in stored))
            raise

    def remove_attachment(
        self,
        *,
        command: RemoveAttachmentCommandDTO,
    ) -> PendingAttachmentsProjectionDTO:
        """Delete a pending file. Return the pending files that stay."""
        removed = self._repository.remove_pending(command=command)
        self._files.delete(paths=(removed.path,))
        return self._queries.get_pending_attachments(
            query=GetPendingAttachmentsQueryDTO(
                conversation_id=removed.conversation_id,
                user_id=command.user_id,
                pending_seconds=self._rules.pending_seconds,
            ),
        )

    def delete_expired_attachments(self) -> int:
        """Delete the expired pending files. Return their number."""
        deleted = self._repository.delete_expired(
            command=DeleteExpiredAttachmentsCommandDTO(
                pending_seconds=self._rules.pending_seconds,
            ),
        )
        self._files.delete(paths=deleted.paths)
        return len(deleted.paths)

    def _checked(
        self,
        *,
        file: UploadedFileDTO,
        conversation_id: str,
    ) -> tuple[NewAttachmentDTO, bytes]:
        """Check the size and the type, and make a large image smaller."""
        name = _clean_name(file.name)
        if not file.data:
            msg = f"{name} is empty."
            raise AttachmentRefused(msg)
        if len(file.data) > self._rules.max_file_bytes:
            megabytes = self._rules.max_file_bytes // (1024 * 1024)
            msg = f"{name} is larger than {megabytes} MB."
            raise AttachmentRefused(msg)
        media_type = media_type_of(name=name, data=file.data)
        if media_type not in self._rules.media_types:
            msg = f"{name} is not a file type that this chat takes."
            raise AttachmentRefused(msg)
        try:
            data, media_type = shrink_image(data=file.data, media_type=media_type)
        except FileCheckError as error:
            msg = f"{name}: {error}"
            raise AttachmentRefused(msg) from error
        attachment_id = new_attachment_id()
        attachment = NewAttachmentDTO(
            attachment_id=attachment_id,
            path=f"{STORAGE_FOLDER}/{conversation_id}/{attachment_id}{SUFFIXES[media_type]}",
            name=name,
            media_type=media_type,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
        return attachment, data

    def _check_conversation_access(
        self,
        *,
        conversation_id: str,
        user_id: UserId,
    ) -> None:
        agent = self._queries.get_conversation_agent(
            query=GetConversationAgentQueryDTO(
                conversation_id=conversation_id,
                user_id=user_id,
            ),
        )
        if agent.agent_name not in self._specs:
            msg = f"No agent has the name {agent.agent_name!r}."
            raise AgentNotFound(msg)
        if not self._permission.can_use(user_id=user_id, agent_name=agent.agent_name):
            msg = f"The user cannot use the agent {agent.agent_name!r}."
            raise AgentAccessDenied(msg)


def _clean_name(name: str) -> str:
    """One line with no folder, so that the label of the prompt stays one line."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    return " ".join(base.split())[:NAME_LENGTH] or "file"
