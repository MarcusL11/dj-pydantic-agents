from unittest import mock
from unittest.mock import create_autospec

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from pydantic_ai.usage import UsageLimits
from unittest_parametrize import param
from unittest_parametrize import parametrize

from dj_pydantic_agents import composition
from dj_pydantic_agents.composition import build_conversation_command_service
from dj_pydantic_agents.composition import build_conversation_query_service
from dj_pydantic_agents.composition import build_event_transport
from dj_pydantic_agents.composition import build_reply_sanitizer
from dj_pydantic_agents.composition import build_turn_run_service
from dj_pydantic_agents.contrib.codex.login_service import PlanLoginService
from dj_pydantic_agents.rendering.nh3_sanitizer import Nh3Sanitizer
from dj_pydantic_agents.services.conversation_command_service import (
    ConversationCommandService,
)
from dj_pydantic_agents.services.conversation_query_service import (
    ConversationQueryService,
)
from dj_pydantic_agents.services.turn_run_service import TurnRunService
from tests.fakes import FakePromptFiles
from tests.fakes import FakeTransport
from tests.testcases import SimpleTestCase


class TestComposition(SimpleTestCase):
    def test_builds_each_service_from_the_settings(self):
        assert isinstance(
            build_conversation_command_service(),
            ConversationCommandService,
        )
        assert isinstance(build_conversation_query_service(), ConversationQueryService)
        assert isinstance(build_turn_run_service(), TurnRunService)

    def test_builds_the_transport_and_the_sanitiser_from_the_settings(self):
        assert isinstance(build_event_transport(), FakeTransport)
        assert isinstance(build_reply_sanitizer(), Nh3Sanitizer)

    @parametrize(
        ("usage_limits", "expected"),
        [
            param(None, None, id="no_limits"),
            param(
                {"request_limit": 60},
                UsageLimits(request_limit=60),
                id="request_limit",
            ),
        ],
    )
    def test_the_turn_run_service_gets_the_usage_limits(self, usage_limits, expected):
        values = {**settings.DJ_PYDANTIC_AGENTS, "USAGE_LIMITS": usage_limits}

        with (
            override_settings(DJ_PYDANTIC_AGENTS=values),
            mock.patch.object(composition, "TurnRunService") as service_class,
        ):
            build_turn_run_service()

        assert service_class.call_args.kwargs["usage_limits"] == expected

    def test_each_service_gets_prompt_files_from_the_settings(self):
        values = {
            **settings.DJ_PYDANTIC_AGENTS,
            "PROMPT_FILES": "tests.fakes.FakePromptFiles",
            "FILE_HISTORY_TURNS": 3,
        }

        with override_settings(DJ_PYDANTIC_AGENTS=values):
            services = (
                build_conversation_command_service(),
                build_conversation_query_service(),
                build_turn_run_service(),
            )

        assert all(
            isinstance(service._prompt_files, FakePromptFiles)  # noqa: SLF001
            for service in services
        )
        assert services[2]._file_history_turns == 3  # noqa: SLF001, PLR2004

    def test_no_prompt_files_by_default(self):
        assert build_turn_run_service()._prompt_files is None  # noqa: SLF001

    @override_settings(DJ_PYDANTIC_AGENTS={})
    def test_a_missing_setting_stops_the_build(self):
        with self.assertRaises(ImproperlyConfigured):
            build_turn_run_service()

    @parametrize(
        ("service_class",),
        [
            param(ConversationCommandService, id="conversation_command"),
            param(ConversationQueryService, id="conversation_query"),
            param(TurnRunService, id="turn_run"),
            param(PlanLoginService, id="plan_login"),
        ],
    )
    def test_a_project_can_autospec_each_service(self, service_class):
        # A project test mocks a service with create_autospec(). It reads the
        # annotations of each method, so each annotation type must load.
        create_autospec(service_class, instance=True)
