"""Read the plan tokens of a user, and refresh them one worker at a time."""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from dj_pydantic_agents.contrib.codex.dtos import GetPlanCredentialQueryDTO
from dj_pydantic_agents.contrib.codex.dtos import PlanCredentialProjectionDTO
from dj_pydantic_agents.contrib.codex.dtos import ReleaseRefreshLeaseCommandDTO
from dj_pydantic_agents.contrib.codex.dtos import SaveRefreshedTokensCommandDTO
from dj_pydantic_agents.contrib.codex.dtos import TakeRefreshLeaseCommandDTO
from dj_pydantic_agents.contrib.codex.errors import PlanNotConnected
from dj_pydantic_agents.contrib.codex.models import PlanCredential


class PlanCredentialRepository:
    def get_credential(
        self,
        *,
        query: GetPlanCredentialQueryDTO,
    ) -> PlanCredentialProjectionDTO:
        encrypted = (
            PlanCredential.objects.filter(user_id=query.user_id)  # type: ignore[misc]
            .values_list("encrypted_tokens", flat=True)
            .first()
        )
        if encrypted is None:
            msg = "The user has no ChatGPT plan login."
            raise PlanNotConnected(msg)
        return PlanCredentialProjectionDTO(encrypted_tokens=encrypted)

    def take_refresh_lease(self, *, command: TakeRefreshLeaseCommandDTO) -> bool:
        """Take the lease if no worker holds it. Return True if this call took it.

        A conditional update, so two workers cannot both take it. A worker that
        stops before save_refreshed_tokens() loses the lease at its end.
        """
        now = timezone.now()
        taken = PlanCredential.objects.filter(
            Q(refresh_lease_until__isnull=True) | Q(refresh_lease_until__lte=now),
            user_id=command.user_id,  # type: ignore[misc]
        ).update(refresh_lease_until=now + timedelta(seconds=command.lease_seconds))
        return bool(taken)

    def release_refresh_lease(self, *, command: ReleaseRefreshLeaseCommandDTO) -> None:
        PlanCredential.objects.filter(user_id=command.user_id).update(  # type: ignore[misc]
            refresh_lease_until=None,
        )

    def save_refreshed_tokens(self, *, command: SaveRefreshedTokensCommandDTO) -> None:
        saved = PlanCredential.objects.filter(user_id=command.user_id).update(  # type: ignore[misc]
            encrypted_tokens=command.encrypted_tokens,
            account_id=command.account_id,
            refresh_lease_until=None,
            updated_at=timezone.now(),
        )
        if not saved:
            msg = "The user has no ChatGPT plan login."
            raise PlanNotConnected(msg)
