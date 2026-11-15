"""MODEL_FACTORY for the ChatGPT plan of each user: the openai-codex provider."""

from typing import TYPE_CHECKING

from django.core.exceptions import ImproperlyConfigured
from pydantic_ai.models.openai_codex import OpenAICodexModel
from pydantic_ai.providers.openai_codex import OpenAICodexProvider

from dj_pydantic_agents.conf import SETTING_NAME
from dj_pydantic_agents.conf import load_settings
from dj_pydantic_agents.contrib.codex.credential_source import PlanCredentialSource

if TYPE_CHECKING:
    from pydantic_ai.models import Model

    from dj_pydantic_agents.dtos.turn_commands import UserId
    from dj_pydantic_agents.kit.roles import ModelRole


class CodexModelFactory:
    """Build the model of a role with the plan tokens of the user.

    MODEL_NAMES maps each role to a model name. The build reads no token: the
    first request does. A user with no tokens then fails the turn with the
    code plan_not_connected. Background mode stays off, because the backend
    cannot resume a background response.
    """

    def build(self, *, role: ModelRole, user_id: UserId) -> Model:
        name = load_settings().model_names.get(role)
        if name is None:
            msg = f"{SETTING_NAME} needs a MODEL_NAMES entry for the role {role!r}."
            raise ImproperlyConfigured(msg)
        provider = OpenAICodexProvider(
            credential_source=PlanCredentialSource(user_id=user_id),
        )
        return OpenAICodexModel(name, provider=provider)
