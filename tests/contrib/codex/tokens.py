"""A fake token endpoint for the plan tests. No test calls OpenAI."""

from dataclasses import dataclass
from typing import Any

from pydantic_ai.providers.openai_codex import OpenAICodexCredentials

TOKEN_REQUEST = "pydantic_ai.providers.openai_codex._post_token_request"  # noqa: S105


def tokens(number: int) -> OpenAICodexCredentials:
    """The tokens with this number, for example access-2 and refresh-2."""
    return OpenAICodexCredentials(
        access_token=f"access-{number}",
        refresh_token=f"refresh-{number}",
        account_id="acct-1",
    )


@dataclass
class FakeTokenResponse:
    access_token: str
    refresh_token: str
    account_id: str = "acct-1"
    id_token: str | None = None


class FakeTokenEndpoint:
    """Record each token request, and answer with new tokens."""

    def __init__(self) -> None:
        self.requests: list[dict[str, str]] = []

    async def __call__(
        self,
        _url: str,
        data: dict[str, str],
        *_args: Any,
        **_kwargs: Any,
    ) -> FakeTokenResponse:
        self.requests.append(data)
        number = len(self.requests)
        return FakeTokenResponse(
            access_token=f"access-{number + 1}",
            refresh_token=f"refresh-{number + 1}",
        )
