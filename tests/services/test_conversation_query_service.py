from unittest.mock import create_autospec

from dj_pydantic_agents.dtos.conversation_queries import GetConversationPageQueryDTO
from dj_pydantic_agents.errors import AgentAccessDenied
from dj_pydantic_agents.permissions import StaffPermission
from dj_pydantic_agents.repositories.conversation_query_repository import (
    ConversationQueryRepository,
)
from dj_pydantic_agents.services.conversation_query_service import (
    ConversationQueryService,
)
from tests.builders import CONVERSATION_ID
from tests.builders import USER_ID
from tests.builders import a_page
from tests.testcases import SimpleTestCase

QUERY = GetConversationPageQueryDTO(conversation_id=CONVERSATION_ID, user_id=USER_ID)


class TestConversationQueryService(SimpleTestCase):
    def setUp(self):
        self.repository = create_autospec(ConversationQueryRepository, instance=True)
        self.repository.get_conversation_page.return_value = a_page()
        self.permission = create_autospec(StaffPermission, instance=True)
        self.service = ConversationQueryService(
            repository=self.repository,
            permission=self.permission,
        )

    def test_returns_the_page_of_an_allowed_user(self):
        self.permission.can_use.return_value = True

        assert self.service.get_conversation_page(query=QUERY) == a_page()
        self.permission.can_use.assert_called_once_with(
            user_id=USER_ID,
            agent_name="assistant",
        )

    def test_a_user_without_access_cannot_read_the_page(self):
        self.permission.can_use.return_value = False

        with self.assertRaises(AgentAccessDenied):
            self.service.get_conversation_page(query=QUERY)
