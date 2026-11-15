import asyncio
from unittest import mock

from pydantic_ai.providers.openai_codex import CredentialsRefreshError
from pydantic_ai.providers.openai_codex import OpenAICodexProvider

from dj_pydantic_agents.contrib.codex import credential_source
from dj_pydantic_agents.contrib.codex.credential_source import PlanCredentialSource
from dj_pydantic_agents.contrib.codex.crypto import decrypt_tokens
from dj_pydantic_agents.contrib.codex.crypto import encrypt_tokens
from dj_pydantic_agents.contrib.codex.errors import PlanNotConnected
from dj_pydantic_agents.contrib.codex.models import PlanCredential
from tests.contrib.codex.tokens import TOKEN_REQUEST
from tests.contrib.codex.tokens import FakeTokenEndpoint
from tests.contrib.codex.tokens import tokens
from tests.factories import UserFactory
from tests.testcases import TestCase

SHORT_WAIT_SECONDS = 0.01


def provider_for(user_id) -> OpenAICodexProvider:
    return OpenAICodexProvider(credential_source=PlanCredentialSource(user_id=user_id))


async def refresh(provider: OpenAICodexProvider):
    """Do the refresh of the provider after a 401 reply, with no model request."""
    await provider._load_if_needed()  # noqa: SLF001
    async with provider._refresh_lock:  # noqa: SLF001
        await provider._refresh_locked()  # noqa: SLF001
    return provider.credentials


class TestPlanCredentialSource(TestCase):
    def setUp(self):
        self.user = UserFactory.create()
        self.other = UserFactory.create()
        self.credential = PlanCredential.objects.create(
            user=self.user,
            encrypted_tokens=encrypt_tokens(tokens(1), user_id=self.user.pk),
            account_id="acct-1",
        )
        self.endpoint = FakeTokenEndpoint()
        for patcher in (
            mock.patch(TOKEN_REQUEST, self.endpoint),
            mock.patch.object(credential_source, "WAIT_SECONDS", SHORT_WAIT_SECONDS),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    async def stored(self):
        credential = await PlanCredential.objects.aget(id=self.credential.id)
        return credential, decrypt_tokens(
            credential.encrypted_tokens,
            user_id=self.user.pk,
        )

    async def test_the_first_load_reads_the_stored_tokens(self):
        source = PlanCredentialSource(user_id=self.user.pk)

        assert await source.load() == tokens(1)

    async def test_two_workers_spend_the_refresh_token_one_time(self):
        first, second = await asyncio.gather(
            refresh(provider_for(self.user.pk)),
            refresh(provider_for(self.user.pk)),
        )

        assert len(self.endpoint.requests) == 1
        assert first == second == tokens(2)
        credential, stored = await self.stored()
        assert stored == tokens(2)
        assert credential.refresh_lease_until is None

    async def test_a_failed_refresh_keeps_the_lease_and_the_tokens(self):
        refused = CredentialsRefreshError("invalid_grant", "openai-codex")

        with (
            mock.patch(TOKEN_REQUEST, side_effect=refused),
            self.assertRaises(CredentialsRefreshError),
        ):
            await refresh(provider_for(self.user.pk))

        credential, stored = await self.stored()
        assert stored == tokens(1)
        assert credential.refresh_lease_until is not None

    async def test_a_user_with_no_tokens_is_not_connected(self):
        source = PlanCredentialSource(user_id=self.other.pk)

        with self.assertRaises(PlanNotConnected):
            await source.load()
