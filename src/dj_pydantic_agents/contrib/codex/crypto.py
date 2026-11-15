"""Encrypt the plan tokens with the Fernet keys of CODEX_TOKEN_KEYS.

The first key encrypts. Each key decrypts, so a new key can go first while
the rows of the old key still decrypt.
"""

from typing import TYPE_CHECKING

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken
from cryptography.fernet import MultiFernet
from pydantic import ValidationError
from pydantic_ai.providers.openai_codex import OpenAICodexCredentials

from dj_pydantic_agents.conf import load_settings
from dj_pydantic_agents.contrib.codex.dtos import PlanTokensDTO
from dj_pydantic_agents.contrib.codex.errors import PlanNotConnected

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dj_pydantic_agents.dtos.turn_commands import UserId


def token_cipher(keys: Sequence[str]) -> MultiFernet:
    """Raise ValueError for a bad key, and for no key."""
    return MultiFernet([Fernet(key) for key in keys])


def encrypt_tokens(credentials: OpenAICodexCredentials, *, user_id: UserId) -> str:
    tokens = PlanTokensDTO(
        access_token=credentials.access_token,
        refresh_token=credentials.refresh_token,
        account_id=credentials.account_id,
        user_id=str(user_id),
    )
    return _cipher().encrypt(tokens.model_dump_json().encode()).decode()


def decrypt_tokens(encrypted: str, *, user_id: UserId) -> OpenAICodexCredentials:
    """Raise PlanNotConnected if no key decrypts the value, or for another user.

    The user check stops a copy of the value to the row of another user.
    """
    try:
        tokens = PlanTokensDTO.model_validate_json(
            _cipher().decrypt(encrypted.encode()),
        )
    except InvalidToken, ValidationError:
        msg = "The stored plan tokens do not decrypt. Log in again."
        raise PlanNotConnected(msg) from None
    if tokens.user_id != str(user_id):
        msg = "The stored plan tokens are of another user. Log in again."
        raise PlanNotConnected(msg)
    return OpenAICodexCredentials(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        account_id=tokens.account_id,
    )


def _cipher() -> MultiFernet:
    return token_cipher(load_settings().codex_token_keys)
