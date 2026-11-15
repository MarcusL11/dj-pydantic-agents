"""Start and complete the plan logins of the users."""

from django.db import transaction
from django.utils import timezone

from dj_pydantic_agents.contrib.codex.dtos import CreatePlanLoginCommandDTO
from dj_pydantic_agents.contrib.codex.dtos import GetPlanLoginQueryDTO
from dj_pydantic_agents.contrib.codex.dtos import PlanLoginProjectionDTO
from dj_pydantic_agents.contrib.codex.dtos import SavePlanCredentialCommandDTO
from dj_pydantic_agents.contrib.codex.errors import PlanLoginFailed
from dj_pydantic_agents.contrib.codex.models import PlanCredential
from dj_pydantic_agents.contrib.codex.models import PlanLogin


class PlanLoginRepository:
    @transaction.atomic
    def create_login(self, *, command: CreatePlanLoginCommandDTO) -> None:
        """Save a new login. Delete the expired logins of the user."""
        PlanLogin.objects.filter(
            user_id=command.user_id,  # type: ignore[misc]
            expires_at__lte=timezone.now(),
        ).delete()
        PlanLogin(  # type: ignore[misc]
            user_id=command.user_id,
            state=command.state,
            code_verifier=command.code_verifier,
            expires_at=command.expires_at,
        ).save(force_insert=True)

    def get_login(self, *, query: GetPlanLoginQueryDTO) -> PlanLoginProjectionDTO:
        """The login of the user with this state. It must not be expired."""
        login = (
            PlanLogin.objects.filter(
                user_id=query.user_id,  # type: ignore[misc]
                state=query.state,
                expires_at__gt=timezone.now(),
            )
            .values("id", "state", "code_verifier")
            .first()
        )
        if login is None:
            msg = "The login is not valid, or it expired. Start the login again."
            raise PlanLoginFailed(msg)
        return PlanLoginProjectionDTO(
            login_id=login["id"],
            state=login["state"],
            code_verifier=login["code_verifier"],
        )

    @transaction.atomic
    def save_credential(self, *, command: SavePlanCredentialCommandDTO) -> None:
        """Replace the tokens of the user, then delete the login."""
        PlanCredential.objects.update_or_create(
            user_id=command.user_id,  # type: ignore[misc]
            defaults={
                "encrypted_tokens": command.encrypted_tokens,
                "account_id": command.account_id,
                "refresh_lease_until": None,
            },
        )
        PlanLogin.objects.filter(id=command.login_id).delete()
