"""Read the conversation page."""

from typing import TYPE_CHECKING

from dj_pydantic_agents.errors import AgentAccessDenied

if TYPE_CHECKING:
    from dj_pydantic_agents.dtos.conversation_queries import (
        ConversationPageProjectionDTO,
    )
    from dj_pydantic_agents.dtos.conversation_queries import GetConversationPageQueryDTO
    from dj_pydantic_agents.extensions import AgentPermission
    from dj_pydantic_agents.repositories.conversation_query_repository import (
        ConversationQueryRepository,
    )


class ConversationQueryService:
    def __init__(
        self,
        *,
        repository: ConversationQueryRepository,
        permission: AgentPermission,
    ) -> None:
        self._repository = repository
        self._permission = permission

    def get_conversation_page(
        self,
        *,
        query: GetConversationPageQueryDTO,
    ) -> ConversationPageProjectionDTO:
        """Only a user who can still use the agent can read the conversation."""
        page = self._repository.get_conversation_page(query=query)
        if not self._permission.can_use(
            user_id=query.user_id,
            agent_name=page.agent_name,
        ):
            msg = f"The user cannot use the agent {page.agent_name!r}."
            raise AgentAccessDenied(msg)
        return page
