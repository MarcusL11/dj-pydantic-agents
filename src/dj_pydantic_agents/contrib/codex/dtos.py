"""The commands, the results and the projections of the plan login and tokens."""

from datetime import datetime  # noqa: TC003

from pydantic import Field

from dj_pydantic_agents.dtos.turn_commands import UserId  # noqa: TC001
from dj_pydantic_agents.kit.dtos import InternalDTO


class StartPlanLoginCommandDTO(InternalDTO):
    user_id: UserId


class PlanLoginStartedResultDTO(InternalDTO):
    authorization_url: str


class CompletePlanLoginCommandDTO(InternalDTO):
    user_id: UserId
    pasted_url: str = Field(min_length=1)


class PlanConnectedResultDTO(InternalDTO):
    account_id: str


class GetPlanStatusQueryDTO(InternalDTO):
    user_id: UserId


class PlanStatusProjectionDTO(InternalDTO):
    """The saved plan of a user. The tokens can still fail at the next request."""

    connected: bool
    account_id: str | None


class CreatePlanLoginCommandDTO(InternalDTO):
    user_id: UserId
    state: str
    code_verifier: str
    expires_at: datetime


class GetPlanLoginQueryDTO(InternalDTO):
    user_id: UserId
    state: str


class PlanLoginProjectionDTO(InternalDTO):
    login_id: str
    state: str
    code_verifier: str


class SavePlanCredentialCommandDTO(InternalDTO):
    """Save the tokens of a completed login, and delete the login."""

    user_id: UserId
    login_id: str
    encrypted_tokens: str
    account_id: str


class GetPlanCredentialQueryDTO(InternalDTO):
    user_id: UserId


class PlanCredentialProjectionDTO(InternalDTO):
    encrypted_tokens: str


class TakeRefreshLeaseCommandDTO(InternalDTO):
    user_id: UserId
    lease_seconds: int = Field(gt=0)


class ReleaseRefreshLeaseCommandDTO(InternalDTO):
    user_id: UserId


class SaveRefreshedTokensCommandDTO(InternalDTO):
    """Save the tokens of a refresh, and end the lease."""

    user_id: UserId
    encrypted_tokens: str
    account_id: str


class PlanTokensDTO(InternalDTO):
    """The JSON inside the encrypted value. user_id binds the value to its row."""

    access_token: str
    refresh_token: str
    account_id: str
    user_id: str
