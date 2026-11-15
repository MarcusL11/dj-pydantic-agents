from unittest import mock

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from pydantic_ai.models.openai_codex import OpenAICodexModel

from dj_pydantic_agents import entry
from dj_pydantic_agents.contrib.codex.model_factory import CodexModelFactory
from dj_pydantic_agents.kit.events import TurnFailedEventDTO
from dj_pydantic_agents.kit.roles import ModelRole
from dj_pydantic_agents.models import Turn
from tests.contrib.codex.tokens import TOKEN_REQUEST
from tests.factories import TurnFactory
from tests.fakes import FakeTransport
from tests.testcases import SimpleTestCase
from tests.testcases import TestCase

USER_ID = 7


def codex_settings(**values):
    return override_settings(
        DJ_PYDANTIC_AGENTS={
            **settings.DJ_PYDANTIC_AGENTS,
            "MODEL_FACTORY": "dj_pydantic_agents.contrib.codex.model_factory."
            "CodexModelFactory",
            "MODEL_NAMES": {"chat": "gpt-6-luna"},
            **values,
        },
    )


class TestCodexModelFactory(SimpleTestCase):
    """SimpleTestCase: the build must not read the database."""

    def test_builds_a_codex_model_with_no_input_or_output(self):
        with (
            codex_settings(),
            mock.patch(TOKEN_REQUEST, side_effect=AssertionError("No token request")),
        ):
            model = CodexModelFactory().build(role=ModelRole.CHAT, user_id=USER_ID)

        assert isinstance(model, OpenAICodexModel)
        assert model.model_name == "gpt-6-luna"
        assert model.system == "openai-codex"

    def test_a_role_with_no_model_name_stops_the_build(self):
        with (
            codex_settings(MODEL_NAMES={}),
            self.assertRaisesRegex(ImproperlyConfigured, "MODEL_NAMES"),
        ):
            CodexModelFactory().build(role=ModelRole.CHAT, user_id=USER_ID)


class TestPlanNotConnected(TestCase):
    def setUp(self):
        FakeTransport.reset()

    def test_a_user_with_no_plan_login_fails_the_turn(self):
        turn = TurnFactory.create()

        with codex_settings():
            entry.run_turn(turn.id)

        turn.refresh_from_db()
        assert turn.status == Turn.Status.FAILED
        assert turn.error_code == "plan_not_connected"
        assert FakeTransport.events[-1] == (
            turn.id,
            TurnFailedEventDTO(error_code="plan_not_connected"),
        )
