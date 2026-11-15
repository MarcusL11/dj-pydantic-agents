"""The query and the projection of the default agent permission."""

from dj_pydantic_agents.dtos.turn_commands import UserId  # noqa: TC001
from dj_pydantic_agents.kit.dtos import InternalDTO


class GetUserAccessQueryDTO(InternalDTO):
    user_id: UserId


class UserAccessProjectionDTO(InternalDTO):
    is_active_staff: bool
