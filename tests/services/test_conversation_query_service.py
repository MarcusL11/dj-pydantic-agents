from unittest.mock import create_autospec

from dj_pydantic_agents.dtos.attachments import AttachmentContentDTO
from dj_pydantic_agents.dtos.attachments import AttachmentFileProjectionDTO
from dj_pydantic_agents.dtos.attachments import GetAttachmentFileQueryDTO
from dj_pydantic_agents.dtos.attachments import GetPendingAttachmentsQueryDTO
from dj_pydantic_agents.dtos.attachments import PendingAttachmentsProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import GetConversationPageQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import ListConversationsQueryDTO
from dj_pydantic_agents.errors import AgentAccessDenied
from dj_pydantic_agents.files import AttachmentFileStore
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
from tests.builders import an_attachment
from tests.testcases import SimpleTestCase

QUERY = GetConversationPageQueryDTO(conversation_id=CONVERSATION_ID, user_id=USER_ID)
LIST_QUERY = ListConversationsQueryDTO(user_id=USER_ID, agent_name="assistant")
PENDING_SECONDS = 3600
FILE_QUERY = GetAttachmentFileQueryDTO(attachment_id="att_1", user_id=USER_ID)
FILE_PATH = "dj_pydantic_agents/attachments/cnv_1/att_1.pdf"


class TestConversationQueryService(SimpleTestCase):
    def setUp(self):
        self.repository = create_autospec(ConversationQueryRepository, instance=True)
        self.repository.get_conversation_page.return_value = a_page()
        self.repository.get_pending_attachments.return_value = (
            PendingAttachmentsProjectionDTO(
                conversation_id=CONVERSATION_ID,
                attachments=(),
            )
        )
        self.permission = create_autospec(StaffPermission, instance=True)
        self.files = create_autospec(AttachmentFileStore, instance=True)
        self.service = ConversationQueryService(
            repository=self.repository,
            permission=self.permission,
            files=self.files,
            pending_attachment_seconds=PENDING_SECONDS,
        )

    def test_returns_the_page_of_an_allowed_user(self):
        self.permission.can_use.return_value = True

        assert self.service.get_conversation_page(query=QUERY) == a_page()
        self.permission.can_use.assert_called_once_with(
            user_id=USER_ID,
            agent_name="assistant",
        )

    def test_the_page_shows_the_pending_files(self):
        self.permission.can_use.return_value = True
        self.repository.get_pending_attachments.return_value = (
            PendingAttachmentsProjectionDTO(
                conversation_id=CONVERSATION_ID,
                attachments=(an_attachment(),),
            )
        )

        page = self.service.get_conversation_page(query=QUERY)

        assert page.pending_attachments == (an_attachment(),)
        self.repository.get_pending_attachments.assert_called_once_with(
            query=GetPendingAttachmentsQueryDTO(
                conversation_id=CONVERSATION_ID,
                user_id=USER_ID,
                pending_seconds=PENDING_SECONDS,
            ),
        )

    def test_returns_the_bytes_of_a_file_to_an_allowed_owner(self):
        self.permission.can_use.return_value = True
        self.repository.get_attachment_file.return_value = AttachmentFileProjectionDTO(
            agent_name="assistant",
            path=FILE_PATH,
            name="invoice.pdf",
            media_type="application/pdf",
        )
        self.files.read.return_value = b"%PDF-1.7"

        content = self.service.get_attachment_content(query=FILE_QUERY)

        assert content == AttachmentContentDTO(
            name="invoice.pdf",
            media_type="application/pdf",
            data=b"%PDF-1.7",
        )
        self.files.read.assert_called_once_with(path=FILE_PATH)

    def test_a_user_without_access_gets_no_file(self):
        self.permission.can_use.return_value = False
        self.repository.get_attachment_file.return_value = AttachmentFileProjectionDTO(
            agent_name="assistant",
            path=FILE_PATH,
            name="invoice.pdf",
            media_type="application/pdf",
        )

        with self.assertRaises(AgentAccessDenied):
            self.service.get_attachment_content(query=FILE_QUERY)
        self.files.read.assert_not_called()

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
