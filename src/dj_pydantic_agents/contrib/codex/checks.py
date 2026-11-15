"""The system check of contrib.codex: the Fernet keys of CODEX_TOKEN_KEYS."""

from typing import TYPE_CHECKING

from django.core.checks import Error
from django.core.checks import register

from dj_pydantic_agents.conf import raw_settings
from dj_pydantic_agents.contrib.codex.crypto import token_cipher

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.apps.config import AppConfig

CHECK_ID = "dj_pydantic_agents.E007"


@register()
def check_token_keys(
    app_configs: Sequence[AppConfig] | None = None,
    **kwargs: object,
) -> list[Error]:
    keys = (raw_settings() or {}).get("CODEX_TOKEN_KEYS")
    if not keys or isinstance(keys, str):
        return [
            Error(
                "contrib.codex needs CODEX_TOKEN_KEYS: a list of Fernet keys.",
                id=CHECK_ID,
            ),
        ]
    try:
        token_cipher(keys)
    except (TypeError, ValueError) as error:
        return [Error(f"CODEX_TOKEN_KEYS has a bad Fernet key: {error}", id=CHECK_ID)]
    return []
