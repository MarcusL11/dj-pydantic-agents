"""Connect the ChatGPT plan of a user, with a copy and paste of an address.

The browser returns to http://localhost:1455/auth/callback after the login.
That page does not load on a server, so the user copies its address and
pastes it into a form of the project.
"""

from datetime import timedelta
from typing import TYPE_CHECKING
from urllib.parse import parse_qs
from urllib.parse import urlsplit

from asgiref.sync import async_to_sync
from django.utils import timezone
from pydantic_ai.providers.openai_codex import CredentialsRefreshError
from pydantic_ai.providers.openai_codex import OpenAICodexOAuthFlow

from dj_pydantic_agents.contrib.codex.crypto import encrypt_tokens
from dj_pydantic_agents.contrib.codex.dtos import CreatePlanLoginCommandDTO
from dj_pydantic_agents.contrib.codex.dtos import GetPlanLoginQueryDTO
from dj_pydantic_agents.contrib.codex.dtos import PlanConnectedResultDTO
from dj_pydantic_agents.contrib.codex.dtos import PlanLoginStartedResultDTO
from dj_pydantic_agents.contrib.codex.dtos import SavePlanCredentialCommandDTO
from dj_pydantic_agents.contrib.codex.errors import PlanLoginFailed

if TYPE_CHECKING:
    from dj_pydantic_agents.contrib.codex.dtos import CompletePlanLoginCommandDTO
    from dj_pydantic_agents.contrib.codex.dtos import GetPlanStatusQueryDTO
    from dj_pydantic_agents.contrib.codex.dtos import PlanStatusProjectionDTO
    from dj_pydantic_agents.contrib.codex.dtos import StartPlanLoginCommandDTO
    from dj_pydantic_agents.contrib.codex.login_repository import PlanLoginRepository

# A login must complete in this time.
LOGIN_SECONDS = 600


class PlanLoginService:
    def __init__(self, *, repository: PlanLoginRepository) -> None:
        self._repository = repository

    def get_plan_status(
        self,
        *,
        query: GetPlanStatusQueryDTO,
    ) -> PlanStatusProjectionDTO:
        """Tell if the user saved a plan. The tokens can still fail later."""
        return self._repository.get_plan_status(query=query)

    def start_login(
        self,
        *,
        command: StartPlanLoginCommandDTO,
    ) -> PlanLoginStartedResultDTO:
        """Save the state and the verifier of a new login. Give its address."""
        flow = OpenAICodexOAuthFlow()
        self._repository.create_login(
            command=CreatePlanLoginCommandDTO(
                user_id=command.user_id,
                state=flow.state,
                code_verifier=flow.code_verifier,
                expires_at=timezone.now() + timedelta(seconds=LOGIN_SECONDS),
            ),
        )
        return PlanLoginStartedResultDTO(authorization_url=flow.authorization_url())

    def complete_login(
        self,
        *,
        command: CompletePlanLoginCommandDTO,
    ) -> PlanConnectedResultDTO:
        """Exchange the code of the pasted address, and save the tokens.

        exchange_code() does not check the state. Here the state selects the
        login of the user, so a wrong state finds no login.
        """
        code, state = _code_and_state(command.pasted_url)
        login = self._repository.get_login(
            query=GetPlanLoginQueryDTO(user_id=command.user_id, state=state),
        )
        flow = OpenAICodexOAuthFlow(state=login.state)
        flow.code_verifier = login.code_verifier
        try:
            credentials = async_to_sync(flow.exchange_code)(code)
        except CredentialsRefreshError as error:
            msg = "ChatGPT did not accept the login. Start the login again."
            raise PlanLoginFailed(msg) from error
        self._repository.save_credential(
            command=SavePlanCredentialCommandDTO(
                user_id=command.user_id,
                login_id=login.login_id,
                encrypted_tokens=encrypt_tokens(credentials, user_id=command.user_id),
                account_id=credentials.account_id,
            ),
        )
        return PlanConnectedResultDTO(account_id=credentials.account_id)


def _code_and_state(pasted_url: str) -> tuple[str, str]:
    query = parse_qs(urlsplit(pasted_url.strip()).query)
    code = query.get("code", [""])[0]
    state = query.get("state", [""])[0]
    if not code or not state:
        msg = "The address has no code. Copy the full address after the login."
        raise PlanLoginFailed(msg)
    return code, state
