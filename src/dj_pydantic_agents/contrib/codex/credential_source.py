"""The plan tokens of one user, for OpenAICodexProvider(credential_source=...).

Refresh tokens are single-use. The provider reads the source again before
each refresh, so this source takes a lease first. Only the worker with the
lease calls the token endpoint. Another worker waits, then gets the new
tokens from the database.
"""

import asyncio
from typing import TYPE_CHECKING

from pydantic_ai.providers.openai_codex import OpenAICodexCredentials
from pydantic_ai.providers.openai_codex import OpenAICodexCredentialSource

from dj_pydantic_agents.contrib.codex.credential_repository import (
    PlanCredentialRepository,
)
from dj_pydantic_agents.contrib.codex.crypto import decrypt_tokens
from dj_pydantic_agents.contrib.codex.crypto import encrypt_tokens
from dj_pydantic_agents.contrib.codex.dtos import GetPlanCredentialQueryDTO
from dj_pydantic_agents.contrib.codex.dtos import ReleaseRefreshLeaseCommandDTO
from dj_pydantic_agents.contrib.codex.dtos import SaveRefreshedTokensCommandDTO
from dj_pydantic_agents.contrib.codex.dtos import TakeRefreshLeaseCommandDTO
from dj_pydantic_agents.db import database_sync_to_async

if TYPE_CHECKING:
    from dj_pydantic_agents.dtos.turn_commands import UserId

# A worker that stops during a refresh holds the lease this long at most.
LEASE_SECONDS = 30
# The wait between two reads while another worker holds the lease.
WAIT_SECONDS = 0.5


class PlanCredentialSource(OpenAICodexCredentialSource):
    def __init__(
        self,
        *,
        user_id: UserId,
        repository: PlanCredentialRepository | None = None,
    ) -> None:
        self._user_id = user_id
        self._repository = repository or PlanCredentialRepository()
        self._current: OpenAICodexCredentials | None = None

    async def load(self) -> OpenAICodexCredentials:
        """The first call reads the tokens. A later call comes before a refresh."""
        if self._current is None:
            self._current = await self._read()
            return self._current
        return await self._load_for_refresh()

    async def save(self, credentials: OpenAICodexCredentials) -> None:
        """Save the tokens of a refresh, and end the lease."""
        await database_sync_to_async(self._repository.save_refreshed_tokens)(
            command=SaveRefreshedTokensCommandDTO(
                user_id=self._user_id,
                encrypted_tokens=encrypt_tokens(credentials, user_id=self._user_id),
                account_id=credentials.account_id,
            ),
        )
        self._current = credentials

    async def _load_for_refresh(self) -> OpenAICodexCredentials:
        """Return new tokens if another worker saved them. Else take the lease.

        With the lease and no new tokens, the provider refreshes, then calls
        save(). If the refresh fails, the lease ends after LEASE_SECONDS.
        """
        while True:
            if await self._take_lease():
                stored = await self._read()
                if stored != self._current:
                    await self._release_lease()
                return self._adopt(stored)
            stored = await self._read()
            if stored != self._current:
                return self._adopt(stored)
            await asyncio.sleep(WAIT_SECONDS)

    def _adopt(self, credentials: OpenAICodexCredentials) -> OpenAICodexCredentials:
        self._current = credentials
        return credentials

    async def _read(self) -> OpenAICodexCredentials:
        stored = await database_sync_to_async(self._repository.get_credential)(
            query=GetPlanCredentialQueryDTO(user_id=self._user_id),
        )
        return decrypt_tokens(stored.encrypted_tokens, user_id=self._user_id)

    async def _take_lease(self) -> bool:
        return await database_sync_to_async(self._repository.take_refresh_lease)(
            command=TakeRefreshLeaseCommandDTO(
                user_id=self._user_id,
                lease_seconds=LEASE_SECONDS,
            ),
        )

    async def _release_lease(self) -> None:
        await database_sync_to_async(self._repository.release_refresh_lease)(
            command=ReleaseRefreshLeaseCommandDTO(user_id=self._user_id),
        )
