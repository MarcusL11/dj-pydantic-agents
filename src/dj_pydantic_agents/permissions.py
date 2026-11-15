"""The default agent permission."""

# Runtime import: create_autospec() reads the annotations of can_use().
from dj_pydantic_agents.dtos.turn_commands import UserId  # noqa: TC001
from dj_pydantic_agents.dtos.user_access import GetUserAccessQueryDTO
from dj_pydantic_agents.repositories.user_access_query_repository import (
    UserAccessQueryRepository,
)


class StaffPermission:
    """Each active staff user can use each agent."""

    def __init__(self) -> None:
        self._repository = UserAccessQueryRepository()

    def can_use(self, *, user_id: UserId, agent_name: str) -> bool:
        access = self._repository.get_user_access(
            query=GetUserAccessQueryDTO(user_id=user_id),
        )
        return access.is_active_staff
