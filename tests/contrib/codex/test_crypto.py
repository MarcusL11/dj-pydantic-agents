from cryptography.fernet import Fernet
from django.conf import settings
from django.test import override_settings

from dj_pydantic_agents.contrib.codex.checks import check_token_keys
from dj_pydantic_agents.contrib.codex.crypto import decrypt_tokens
from dj_pydantic_agents.contrib.codex.crypto import encrypt_tokens
from dj_pydantic_agents.contrib.codex.errors import PlanNotConnected
from tests.contrib.codex.tokens import tokens
from tests.testcases import SimpleTestCase

CREDENTIALS = tokens(1)
USER_ID = 7
OLD_KEY = settings.DJ_PYDANTIC_AGENTS["CODEX_TOKEN_KEYS"][0]


def with_keys(keys):
    return override_settings(
        DJ_PYDANTIC_AGENTS={**settings.DJ_PYDANTIC_AGENTS, "CODEX_TOKEN_KEYS": keys},
    )


class TestTokenCrypto(SimpleTestCase):
    def test_encrypts_and_decrypts_the_tokens(self):
        encrypted = encrypt_tokens(CREDENTIALS, user_id=USER_ID)

        assert "refresh-1" not in encrypted
        assert decrypt_tokens(encrypted, user_id=USER_ID) == CREDENTIALS

    def test_a_new_first_key_still_decrypts_the_old_value(self):
        encrypted = encrypt_tokens(CREDENTIALS, user_id=USER_ID)
        new_key = Fernet.generate_key().decode()

        with with_keys([new_key, OLD_KEY]):
            assert decrypt_tokens(encrypted, user_id=USER_ID) == CREDENTIALS
            reencrypted = encrypt_tokens(CREDENTIALS, user_id=USER_ID)
        with with_keys([new_key]):
            assert decrypt_tokens(reencrypted, user_id=USER_ID) == CREDENTIALS

    def test_a_value_of_another_key_does_not_decrypt(self):
        encrypted = encrypt_tokens(CREDENTIALS, user_id=USER_ID)

        with (
            with_keys([Fernet.generate_key().decode()]),
            self.assertRaises(PlanNotConnected),
        ):
            decrypt_tokens(encrypted, user_id=USER_ID)

    def test_a_value_of_another_user_does_not_decrypt(self):
        encrypted = encrypt_tokens(CREDENTIALS, user_id=USER_ID)

        with self.assertRaisesRegex(PlanNotConnected, "another user"):
            decrypt_tokens(encrypted, user_id=USER_ID + 1)


class TestCheckTokenKeys(SimpleTestCase):
    def check_ids(self, keys):
        with with_keys(keys):
            return [error.id for error in check_token_keys()]

    def test_valid_keys_pass(self):
        assert self.check_ids([OLD_KEY, Fernet.generate_key().decode()]) == []

    def test_no_key_fails(self):
        assert self.check_ids([]) == ["dj_pydantic_agents.E007"]

    def test_one_string_is_not_a_list(self):
        assert self.check_ids(OLD_KEY) == ["dj_pydantic_agents.E007"]

    def test_a_bad_key_fails(self):
        assert self.check_ids([OLD_KEY, "not-a-key"]) == ["dj_pydantic_agents.E007"]
