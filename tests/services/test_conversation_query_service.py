from unittest.mock import create_autospec

from dj_pydantic_agents.dtos.conversation_queries import GetConversationPageQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import ListConversationsQueryDTO
from dj_pydantic_agents.errors import AgentAccessDenied
from dj_pydantic_agents.kit.transcript import TranscriptLineDTO
from dj_pydantic_agents.permissions import StaffPermission
from dj_pydantic_agents.repositories.conversation_query_repository import (
    ConversationQueryRepository,
)
from dj_pydantic_agents.services.conversation_query_service import (
    ConversationQueryService,
)
from tests.builders import CONVERSATION_ID
from tests.builders import FILE_ID
from tests.builders import USER_ID
from tests.builders import a_file_ref
from tests.builders import a_page
from tests.fakes import FakePromptFiles
from tests.testcases import SimpleTestCase

QUERY = GetConversationPageQueryDTO(conversation_id=CONVERSATION_ID, user_id=USER_ID)
LIST_QUERY = ListConversationsQueryDTO(user_id=USER_ID, agent_name="assistant")


class TestConversationQueryService(SimpleTestCase):
    def setUp(self):
        self.repository = create_autospec(ConversationQueryRepository, instance=True)
        self.repository.get_conversation_page.return_value = a_page()
        self.permission = create_autospec(StaffPermission, instance=True)
        self.prompt_files = create_autospec(FakePromptFiles, instance=True)
        self.service = ConversationQueryService(
            repository=self.repository,
            permission=self.permission,
        )

    def files_service(self) -> ConversationQueryService:
        return ConversationQueryService(
            repository=self.repository,
            permission=self.permission,
            prompt_files=self.prompt_files,
        )

    def test_the_page_gets_the_pending_files(self):
        self.permission.can_use.return_value = True
        self.prompt_files.pending.return_value = (a_file_ref(),)

        page = self.files_service().get_conversation_page(query=QUERY)

        assert page.pending_files == (a_file_ref(),)
        self.prompt_files.pending.assert_called_once_with(
            conversation_id=CONVERSATION_ID,
            user_id=USER_ID,
        )
        self.prompt_files.describe.assert_not_called()

    def test_the_project_describes_the_files_of_the_transcript(self):
        self.permission.can_use.return_value = True
        lost = a_file_ref(file_id="fil_lost", name="old.pdf")
        self.repository.get_conversation_page.return_value = a_page(
            lines=(
                TranscriptLineDTO(kind="user", text="Read", files=(a_file_ref(), lost)),
                TranscriptLineDTO(kind="assistant", text="Done."),
            ),
        )
        described = a_file_ref(size=1403, url="/files/fil_1/")
        self.prompt_files.describe.return_value = (described,)
        self.prompt_files.pending.return_value = ()

        page = self.files_service().get_conversation_page(query=QUERY)

        self.prompt_files.describe.assert_called_once_with(
            file_ids=(FILE_ID, "fil_lost"),
        )
        # The project does not know the lost file. It keeps its name from the history.
        assert page.lines[0].files == (described, lost)
        assert page.lines[1].files == ()

    def test_a_user_without_access_gets_no_files(self):
        self.permission.can_use.return_value = False

        with self.assertRaises(AgentAccessDenied):
            self.files_service().get_conversation_page(query=QUERY)

        self.prompt_files.pending.assert_not_called()

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

    def test_lists_the_conversations_of_an_allowed_user(self):
        self.permission.can_use.return_value = True
        self.repository.list_conversations.return_value = ()

        assert self.service.list_conversations(query=LIST_QUERY) == ()
        self.permission.can_use.assert_called_once_with(
            user_id=USER_ID,
            agent_name="assistant",
        )
        self.repository.list_conversations.assert_called_once_with(query=LIST_QUERY)

    def test_a_user_without_access_cannot_list_the_conversations(self):
        self.permission.can_use.return_value = False

        with self.assertRaises(AgentAccessDenied):
            self.service.list_conversations(query=LIST_QUERY)
        self.repository.list_conversations.assert_not_called()
