"""Read the access of a user, for the default agent permission."""

from django.contrib.auth import get_user_model

from dj_pydantic_agents.dtos.user_access import GetUserAccessQueryDTO
from dj_pydantic_agents.dtos.user_access import UserAccessProjectionDTO


class UserAccessQueryRepository:
    def get_user_access(
        self,
        *,
        query: GetUserAccessQueryDTO,
    ) -> UserAccessProjectionDTO:
        is_active_staff = (
            get_user_model()
            .objects.filter(
                pk=query.user_id,  # type: ignore[misc]
                is_active=True,
                is_staff=True,
            )
            .exists()
        )
        return UserAccessProjectionDTO(is_active_staff=is_active_staff)
