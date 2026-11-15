from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from dj_pydantic_agents.composition import build_conversation_command_service
from dj_pydantic_agents.composition import build_conversation_query_service
from dj_pydantic_agents.composition import build_turn_run_service
from dj_pydantic_agents.services.conversation_command_service import (
    ConversationCommandService,
)
from dj_pydantic_agents.services.conversation_query_service import (
    ConversationQueryService,
)
from dj_pydantic_agents.services.turn_run_service import TurnRunService
from tests.testcases import SimpleTestCase


class TestComposition(SimpleTestCase):
    def test_builds_each_service_from_the_settings(self):
        assert isinstance(
            build_conversation_command_service(),
            ConversationCommandService,
        )
        assert isinstance(build_conversation_query_service(), ConversationQueryService)
        assert isinstance(build_turn_run_service(), TurnRunService)

    @override_settings(DJ_PYDANTIC_AGENTS={})
    def test_a_missing_setting_stops_the_build(self):
        with self.assertRaises(ImproperlyConfigured):
            build_turn_run_service()
