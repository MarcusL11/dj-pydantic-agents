from unittest import mock
from unittest.mock import create_autospec

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from pydantic_ai.usage import UsageLimits
from unittest_parametrize import param
from unittest_parametrize import parametrize

from dj_pydantic_agents import composition
from dj_pydantic_agents.composition import build_attachment_command_service
from dj_pydantic_agents.composition import build_conversation_command_service
from dj_pydantic_agents.composition import build_conversation_query_service
from dj_pydantic_agents.composition import build_event_transport
from dj_pydantic_agents.composition import build_reply_sanitizer
from dj_pydantic_agents.composition import build_turn_run_service
from dj_pydantic_agents.contrib.codex.login_service import PlanLoginService
from dj_pydantic_agents.rendering.nh3_sanitizer import Nh3Sanitizer
from dj_pydantic_agents.services.attachment_command_service import (
    AttachmentCommandService,
)
from dj_pydantic_agents.services.conversation_command_service import (
    ConversationCommandService,
)
from dj_pydantic_agents.services.conversation_query_service import (
    ConversationQueryService,
)
from dj_pydantic_agents.services.turn_run_service import TurnRunService
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
        assert isinstance(build_attachment_command_service(), AttachmentCommandService)

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
            param(AttachmentCommandService, id="attachment_command"),
            param(PlanLoginService, id="plan_login"),
        ],
    )
    def test_a_project_can_autospec_each_service(self, service_class):
        # A project test mocks a service with create_autospec(). It reads the
        # annotations of each method, so each annotation type must load.
        create_autospec(service_class, instance=True)
