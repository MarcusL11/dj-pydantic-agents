from datetime import timedelta
from typing import TYPE_CHECKING
from unittest import mock
from urllib.parse import parse_qs
from urllib.parse import urlsplit

from django.utils import timezone
from pydantic_ai.providers.openai_codex import CredentialsRefreshError

from dj_pydantic_agents.contrib.codex.composition import build_plan_login_service
from dj_pydantic_agents.contrib.codex.crypto import decrypt_tokens
from dj_pydantic_agents.contrib.codex.dtos import CompletePlanLoginCommandDTO
from dj_pydantic_agents.contrib.codex.dtos import StartPlanLoginCommandDTO
from dj_pydantic_agents.contrib.codex.errors import PlanLoginFailed
from dj_pydantic_agents.contrib.codex.models import PlanCredential
from dj_pydantic_agents.contrib.codex.models import PlanLogin
from tests.contrib.codex.tokens import TOKEN_REQUEST
from tests.contrib.codex.tokens import FakeTokenEndpoint
from tests.contrib.codex.tokens import tokens
from tests.factories import UserFactory
from tests.testcases import TestCase

if TYPE_CHECKING:
    from django.contrib.auth.models import User

CALLBACK = "http://localhost:1455/auth/callback"


class TestPlanLoginService(TestCase):
    user: User

    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()

    def setUp(self):
        self.endpoint = FakeTokenEndpoint()
        patcher = mock.patch(TOKEN_REQUEST, self.endpoint)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.service = build_plan_login_service()

    def start(self, user=None) -> dict[str, list[str]]:
        started = self.service.start_login(
            command=StartPlanLoginCommandDTO(user_id=(user or self.user).pk),
        )
        return parse_qs(urlsplit(started.authorization_url).query)

    def complete(self, *, state, code="code-1", user=None):
        return self.service.complete_login(
            command=CompletePlanLoginCommandDTO(
                user_id=(user or self.user).pk,
                pasted_url=f"{CALLBACK}?code={code}&state={state}",
            ),
        )

    def test_start_saves_the_state_and_the_verifier_of_the_address(self):
        params = self.start()

        login = PlanLogin.objects.get(user=self.user)
        assert params["state"] == [login.state]
        assert params["code_challenge_method"] == ["S256"]
        assert login.expires_at > timezone.now()

    def test_complete_sends_the_stored_verifier_and_saves_the_tokens(self):
        params = self.start()
        login = PlanLogin.objects.get(user=self.user)

        connected = self.complete(state=params["state"][0])

        (request,) = self.endpoint.requests
        assert request["code"] == "code-1"
        assert request["code_verifier"] == login.code_verifier
        assert connected.account_id == "acct-1"
        credential = PlanCredential.objects.get(user=self.user)
        assert "access-2" not in credential.encrypted_tokens
        assert decrypt_tokens(
            credential.encrypted_tokens,
            user_id=self.user.pk,
        ) == tokens(2)
        assert not PlanLogin.objects.exists()

    def test_a_wrong_state_fails_and_calls_no_endpoint(self):
        self.start()

        with self.assertRaises(PlanLoginFailed):
            self.complete(state="not-the-state")

        assert self.endpoint.requests == []

    def test_an_expired_login_fails(self):
        params = self.start()
        PlanLogin.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        with self.assertRaises(PlanLoginFailed):
            self.complete(state=params["state"][0])

    def test_the_login_of_another_user_fails(self):
        params = self.start()

        with self.assertRaises(PlanLoginFailed):
            self.complete(state=params["state"][0], user=UserFactory.create())

        assert not PlanCredential.objects.exists()

    def test_an_address_without_a_code_fails(self):
        self.start()

        with self.assertRaises(PlanLoginFailed):
            self.service.complete_login(
                command=CompletePlanLoginCommandDTO(
                    user_id=self.user.pk,
                    pasted_url=f"{CALLBACK}?error=access_denied",
                ),
            )

    def test_a_refused_code_fails_and_keeps_the_login(self):
        params = self.start()
        refused = CredentialsRefreshError("invalid_grant", "openai-codex")

        with (
            mock.patch(TOKEN_REQUEST, side_effect=refused),
            self.assertRaises(PlanLoginFailed),
        ):
            self.complete(state=params["state"][0])

        assert PlanLogin.objects.filter(user=self.user).exists()

    def test_a_new_start_deletes_the_expired_logins(self):
        self.start()
        PlanLogin.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        self.start()

        assert PlanLogin.objects.filter(user=self.user).count() == 1
