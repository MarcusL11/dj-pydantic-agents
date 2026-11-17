import hashlib
from dataclasses import replace
from unittest import mock
from unittest.mock import create_autospec

from unittest_parametrize import param
from unittest_parametrize import parametrize

from dj_pydantic_agents.dtos.attachments import AttachmentFilesResultDTO
from dj_pydantic_agents.dtos.attachments import AttachmentRemovedResultDTO
from dj_pydantic_agents.dtos.attachments import DeleteExpiredAttachmentsCommandDTO
from dj_pydantic_agents.dtos.attachments import GetPendingAttachmentsQueryDTO
from dj_pydantic_agents.dtos.attachments import PendingAttachmentsProjectionDTO
from dj_pydantic_agents.dtos.attachments import RemoveAttachmentCommandDTO
from dj_pydantic_agents.dtos.attachments import UploadAttachmentsCommandDTO
from dj_pydantic_agents.dtos.attachments import UploadedFileDTO
from dj_pydantic_agents.errors import AgentAccessDenied
from dj_pydantic_agents.errors import AttachmentRefused
from dj_pydantic_agents.files import AttachmentFileStore
from dj_pydantic_agents.kit.file_checks import IMAGE_SHRINK_BYTES
from dj_pydantic_agents.kit.file_checks import SUPPORTED_MEDIA_TYPES
from dj_pydantic_agents.permissions import StaffPermission
from dj_pydantic_agents.repositories.attachment_command_repository import (
    AttachmentCommandRepository,
)
from dj_pydantic_agents.repositories.conversation_query_repository import (
    ConversationQueryRepository,
)
from dj_pydantic_agents.services import attachment_command_service
from dj_pydantic_agents.services.attachment_command_service import (
    AttachmentCommandService,
)
from dj_pydantic_agents.services.attachment_command_service import AttachmentRules
from tests.builders import ATTACHMENT_ID
from tests.builders import CONVERSATION_ID
from tests.builders import USER_ID
from tests.builders import an_agent
from tests.builders import an_attachment
from tests.fakes import ASSISTANT_SPEC
from tests.testcases import SimpleTestCase

PDF_BYTES = b"%PDF-1.7 invoice"
PENDING_SECONDS = 3600
RULES = AttachmentRules(
    media_types=SUPPORTED_MEDIA_TYPES,
    max_files=2,
    max_file_bytes=6 * 1024 * 1024,
    max_message_bytes=20 * 1024 * 1024,
    pending_seconds=PENDING_SECONDS,
)
PENDING = PendingAttachmentsProjectionDTO(
    conversation_id=CONVERSATION_ID,
    attachments=(an_attachment(),),
)


def upload(*files: UploadedFileDTO) -> UploadAttachmentsCommandDTO:
    return UploadAttachmentsCommandDTO(
        conversation_id=CONVERSATION_ID,
        user_id=USER_ID,
        files=files,
    )


class TestAttachmentCommandService(SimpleTestCase):
    def setUp(self):
        self.repository = create_autospec(AttachmentCommandRepository, instance=True)
        self.repository.add_pending.return_value = PENDING
        self.queries = create_autospec(ConversationQueryRepository, instance=True)
        self.queries.get_conversation_agent.return_value = an_agent()
        self.files = create_autospec(AttachmentFileStore, instance=True)
        self.files.save.side_effect = lambda *, path, data: path
        self.permission = create_autospec(StaffPermission, instance=True)
        self.permission.can_use.return_value = True

    def service(self, rules: AttachmentRules = RULES) -> AttachmentCommandService:
        return AttachmentCommandService(
            repository=self.repository,
            queries=self.queries,
            files=self.files,
            specs={"assistant": ASSISTANT_SPEC},
            permission=self.permission,
            rules=rules,
        )

    def test_stores_a_checked_file_and_adds_its_pending_row(self):
        with mock.patch.object(
            attachment_command_service,
            "new_attachment_id",
            return_value=ATTACHMENT_ID,
        ):
            pending = self.service().upload_attachments(
                command=upload(
                    UploadedFileDTO(name="C:\\scans\\in\nvoice.pdf", data=PDF_BYTES),
                ),
            )

        assert pending == PENDING
        path = f"dj_pydantic_agents/attachments/{CONVERSATION_ID}/{ATTACHMENT_ID}.pdf"
        self.files.save.assert_called_once_with(path=path, data=PDF_BYTES)
        command = self.repository.add_pending.call_args.kwargs["command"]
        [attachment] = command.attachments
        assert attachment.name == "in voice.pdf"
        assert attachment.path == path
        assert attachment.media_type == "application/pdf"
        assert attachment.size == len(PDF_BYTES)
        assert attachment.sha256 == hashlib.sha256(PDF_BYTES).hexdigest()
        assert (command.max_files, command.max_bytes, command.pending_seconds) == (
            RULES.max_files,
            RULES.max_message_bytes,
            PENDING_SECONDS,
        )

    def test_a_repository_refusal_deletes_the_stored_files(self):
        self.repository.add_pending.side_effect = AttachmentRefused("Too many files.")

        with self.assertRaises(AttachmentRefused):
            self.service().upload_attachments(
                command=upload(UploadedFileDTO(name="a.pdf", data=PDF_BYTES)),
            )

        [stored_path] = self.files.delete.call_args.kwargs["paths"]
        assert stored_path.endswith(".pdf")

    def test_a_large_image_is_stored_smaller(self):
        with mock.patch.object(
            attachment_command_service,
            "shrink_image",
            return_value=(b"\xff\xd8\xff small", "image/jpeg"),
        ) as shrink:
            self.service().upload_attachments(
                command=upload(
                    UploadedFileDTO(name="dial.png", data=b"\x89PNG\r\n\x1a\n"),
                ),
            )

        shrink.assert_called_once()
        path = self.files.save.call_args.kwargs["path"]
        assert path.endswith(".jpg")
        command = self.repository.add_pending.call_args.kwargs["command"]
        assert command.attachments[0].media_type == "image/jpeg"

    def test_an_image_that_does_not_shrink_is_refused(self):
        data = b"GIF89a" + b"\0" * IMAGE_SHRINK_BYTES

        with self.assertRaisesRegex(AttachmentRefused, "dial.gif: A GIF image"):
            self.service().upload_attachments(
                command=upload(UploadedFileDTO(name="dial.gif", data=data)),
            )

    def test_one_bad_file_stores_nothing(self):
        with self.assertRaisesRegex(AttachmentRefused, "tool.exe is not a file type"):
            self.service().upload_attachments(
                command=upload(
                    UploadedFileDTO(name="a.pdf", data=PDF_BYTES),
                    UploadedFileDTO(name="tool.exe", data=b"MZ"),
                ),
            )

        self.files.save.assert_not_called()
        self.repository.add_pending.assert_not_called()

    @parametrize(
        ("rules", "files", "message"),
        [
            param(
                RULES,
                (UploadedFileDTO(name="a.pdf", data=b""),),
                "a.pdf is empty",
                id="empty",
            ),
            param(
                RULES,
                (
                    UploadedFileDTO(
                        name="a.pdf",
                        data=b"%PDF" + b"\0" * RULES.max_file_bytes,
                    ),
                ),
                "larger than 6 MB",
                id="large_file",
            ),
            param(
                RULES,
                tuple(UploadedFileDTO(name="a.pdf", data=PDF_BYTES) for _ in range(3)),
                "2 files at most",
                id="many_files",
            ),
            param(
                replace(RULES, media_types=("image/png",)),
                (UploadedFileDTO(name="a.pdf", data=PDF_BYTES),),
                "not a file type",
                id="other_type",
            ),
            param(
                replace(RULES, media_types=()),
                (UploadedFileDTO(name="a.pdf", data=PDF_BYTES),),
                "takes no files",
                id="no_types",
            ),
        ],
    )
    def test_a_refusal_comes_before_any_store(self, rules, files, message):
        with self.assertRaisesRegex(AttachmentRefused, message):
            self.service(rules).upload_attachments(command=upload(*files))

        self.files.save.assert_not_called()

    def test_a_denied_user_uploads_nothing(self):
        self.permission.can_use.return_value = False

        with self.assertRaises(AgentAccessDenied):
            self.service().upload_attachments(
                command=upload(UploadedFileDTO(name="a.pdf", data=PDF_BYTES)),
            )

        self.files.save.assert_not_called()

    def test_a_removal_deletes_the_file_and_lists_the_rest(self):
        self.repository.remove_pending.return_value = AttachmentRemovedResultDTO(
            conversation_id=CONVERSATION_ID,
            path="dj_pydantic_agents/attachments/a.pdf",
        )
        self.queries.get_pending_attachments.return_value = PENDING
        command = RemoveAttachmentCommandDTO(
            attachment_id=ATTACHMENT_ID,
            user_id=USER_ID,
        )

        assert self.service().remove_attachment(command=command) == PENDING
        self.files.delete.assert_called_once_with(
            paths=("dj_pydantic_agents/attachments/a.pdf",),
        )
        self.queries.get_pending_attachments.assert_called_once_with(
            query=GetPendingAttachmentsQueryDTO(
                conversation_id=CONVERSATION_ID,
                user_id=USER_ID,
                pending_seconds=PENDING_SECONDS,
            ),
        )

    def test_the_cleanup_deletes_the_expired_files(self):
        self.repository.delete_expired.return_value = AttachmentFilesResultDTO(
            paths=("a.pdf", "b.png"),
        )

        assert self.service().delete_expired_attachments() == 2  # noqa: PLR2004
        self.repository.delete_expired.assert_called_once_with(
            command=DeleteExpiredAttachmentsCommandDTO(pending_seconds=PENDING_SECONDS),
        )
        self.files.delete.assert_called_once_with(paths=("a.pdf", "b.png"))
