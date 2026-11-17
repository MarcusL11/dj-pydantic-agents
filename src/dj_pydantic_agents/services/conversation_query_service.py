"""Read the conversation pages."""

# create_autospec() reads the annotations of each method, so the annotation
# types load at runtime.
# ruff: noqa: TC001

from dj_pydantic_agents.dtos.attachments import AttachmentContentDTO
from dj_pydantic_agents.dtos.attachments import GetAttachmentFileQueryDTO
from dj_pydantic_agents.dtos.attachments import GetPendingAttachmentsQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import ConversationPageProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import (
    ConversationSummaryProjectionDTO,
)
from dj_pydantic_agents.dtos.conversation_queries import GetConversationPageQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import ListConversationsQueryDTO
from dj_pydantic_agents.dtos.turn_commands import UserId
from dj_pydantic_agents.errors import AgentAccessDenied
from dj_pydantic_agents.extensions import AgentPermission
from dj_pydantic_agents.files import AttachmentFileStore
from dj_pydantic_agents.repositories.conversation_query_repository import (
    ConversationQueryRepository,
)


class ConversationQueryService:
    def __init__(
        self,
        *,
        repository: ConversationQueryRepository,
        permission: AgentPermission,
        files: AttachmentFileStore,
        pending_attachment_seconds: int,
    ) -> None:
        self._repository = repository
        self._permission = permission
        self._files = files
        self._pending_attachment_seconds = pending_attachment_seconds

    def list_conversations(
        self,
        *,
        query: ListConversationsQueryDTO,
    ) -> tuple[ConversationSummaryProjectionDTO, ...]:
        """The conversations of the user with the agent, newest first."""
        self._check_access(user_id=query.user_id, agent_name=query.agent_name)
        return self._repository.list_conversations(query=query)

    def get_conversation_page(
        self,
        *,
        query: GetConversationPageQueryDTO,
    ) -> ConversationPageProjectionDTO:
        """Only a user who can still use the agent can read the conversation."""
        page = self._repository.get_conversation_page(query=query)
        self._check_access(user_id=query.user_id, agent_name=page.agent_name)
        pending = self._repository.get_pending_attachments(
            query=GetPendingAttachmentsQueryDTO(
                conversation_id=query.conversation_id,
                user_id=query.user_id,
                pending_seconds=self._pending_attachment_seconds,
            ),
        )
        return page.model_copy(update={"pending_attachments": pending.attachments})

    def get_attachment_content(
        self,
        *,
        query: GetAttachmentFileQueryDTO,
    ) -> AttachmentContentDTO:
        """The bytes of a file. Only the owner who can use the agent gets them."""
        file = self._repository.get_attachment_file(query=query)
        self._check_access(user_id=query.user_id, agent_name=file.agent_name)
        return AttachmentContentDTO(
            name=file.name,
            media_type=file.media_type,
            data=self._files.read(path=file.path),
        )

    def _check_access(self, *, user_id: UserId, agent_name: str) -> None:
        if not self._permission.can_use(user_id=user_id, agent_name=agent_name):
            msg = f"The user cannot use the agent {agent_name!r}."
            raise AgentAccessDenied(msg)
