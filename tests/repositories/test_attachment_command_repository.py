from datetime import timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

from dj_pydantic_agents.dtos.attachments import AddPendingAttachmentsCommandDTO
from dj_pydantic_agents.dtos.attachments import DeleteExpiredAttachmentsCommandDTO
from dj_pydantic_agents.dtos.attachments import NewAttachmentDTO
from dj_pydantic_agents.dtos.attachments import RemoveAttachmentCommandDTO
from dj_pydantic_agents.errors import AttachmentNotPending
from dj_pydantic_agents.errors import AttachmentRefused
from dj_pydantic_agents.errors import ConversationNotFound
from dj_pydantic_agents.ids import new_attachment_id
from dj_pydantic_agents.models import Attachment
from dj_pydantic_agents.models import Turn
from dj_pydantic_agents.repositories.attachment_command_repository import (
    AttachmentCommandRepository,
)
from tests.factories import AttachmentFactory
from tests.factories import ConversationFactory
from tests.factories import TurnFactory
from tests.factories import UserFactory
from tests.testcases import TestCase

if TYPE_CHECKING:
    from django.contrib.auth.models import User

    from dj_pydantic_agents.models import Conversation

PENDING_SECONDS = 3600
MAX_FILES = 2
MAX_BYTES = 100


def a_new_attachment(*, size: int = 10, name: str = "invoice.pdf") -> NewAttachmentDTO:
    attachment_id = new_attachment_id()
    return NewAttachmentDTO(
        attachment_id=attachment_id,
        path=f"dj_pydantic_agents/attachments/{attachment_id}.pdf",
        name=name,
        media_type="application/pdf",
        size=size,
        sha256="a" * 64,
    )


class TestAddPending(TestCase):
    owner: User
    conversation: Conversation

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create()
        cls.conversation = ConversationFactory.create(owner=cls.owner)

    def add(self, *attachments: NewAttachmentDTO, user_id: int | None = None):
        return AttachmentCommandRepository().add_pending(
            command=AddPendingAttachmentsCommandDTO(
                conversation_id=self.conversation.id,
                user_id=self.owner.pk if user_id is None else user_id,
                attachments=attachments,
                max_files=MAX_FILES,
                max_bytes=MAX_BYTES,
                pending_seconds=PENDING_SECONDS,
            ),
        )

    def test_adds_pending_rows_and_lists_all_pending_files(self):
        earlier = AttachmentFactory.create(
            conversation=self.conversation,
            uploaded_by=self.owner,
        )
        new = a_new_attachment(name="dial.pdf")

        pending = self.add(new)

        assert [file.attachment_id for file in pending.attachments] == [
            earlier.id,
            new.attachment_id,
        ]
        row = Attachment.objects.get(id=new.attachment_id)
        assert row.turn is None
        assert row.uploaded_by == self.owner
        assert str(row.file) == new.path
        assert (row.name, row.size, row.sha256) == ("dial.pdf", 10, "a" * 64)

    def test_too_many_files_add_nothing(self):
        AttachmentFactory.create(conversation=self.conversation, uploaded_by=self.owner)

        with self.assertRaisesRegex(AttachmentRefused, "2 files"):
            self.add(a_new_attachment(), a_new_attachment())

        assert Attachment.objects.count() == 1

    def test_too_many_bytes_add_nothing(self):
        AttachmentFactory.create(
            conversation=self.conversation,
            uploaded_by=self.owner,
            size=95,
        )

        with self.assertRaises(AttachmentRefused):
            self.add(a_new_attachment(size=6))

        assert Attachment.objects.count() == 1

    def test_expired_and_sent_files_do_not_count(self):
        expired = AttachmentFactory.create(
            conversation=self.conversation,
            uploaded_by=self.owner,
        )
        Attachment.objects.filter(id=expired.id).update(
            created_at=timezone.now() - timedelta(seconds=PENDING_SECONDS + 1),
        )
        AttachmentFactory.create(
            conversation=self.conversation,
            uploaded_by=self.owner,
            turn=TurnFactory.create(
                conversation=self.conversation,
                status=Turn.Status.DONE,
            ),
        )

        pending = self.add(a_new_attachment(), a_new_attachment())

        assert len(pending.attachments) == MAX_FILES

    def test_another_user_gets_not_found(self):
        with self.assertRaises(ConversationNotFound):
            self.add(a_new_attachment(), user_id=UserFactory.create().pk)

        assert not Attachment.objects.exists()


class TestRemovePending(TestCase):
    owner: User
    conversation: Conversation

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create()
        cls.conversation = ConversationFactory.create(owner=cls.owner)

    def remove(self, attachment_id: str, *, user_id: int | None = None):
        return AttachmentCommandRepository().remove_pending(
            command=RemoveAttachmentCommandDTO(
                attachment_id=attachment_id,
                user_id=self.owner.pk if user_id is None else user_id,
            ),
        )

    def test_deletes_a_pending_file_and_gives_its_path(self):
        file = AttachmentFactory.create(
            conversation=self.conversation,
            uploaded_by=self.owner,
        )

        removed = self.remove(file.id)

        assert (removed.conversation_id, removed.path) == (
            self.conversation.id,
            str(file.file),
        )
        assert not Attachment.objects.exists()

    def test_a_sent_file_stays(self):
        file = AttachmentFactory.create(
            conversation=self.conversation,
            uploaded_by=self.owner,
            turn=TurnFactory.create(
                conversation=self.conversation,
                status=Turn.Status.DONE,
            ),
        )

        with self.assertRaises(AttachmentNotPending):
            self.remove(file.id)

        assert Attachment.objects.filter(id=file.id).exists()

    def test_another_user_removes_nothing(self):
        file = AttachmentFactory.create(
            conversation=self.conversation,
            uploaded_by=self.owner,
        )

        with self.assertRaises(AttachmentNotPending):
            self.remove(file.id, user_id=UserFactory.create().pk)

        assert Attachment.objects.filter(id=file.id).exists()


class TestDeleteExpired(TestCase):
    def test_deletes_only_the_expired_pending_files(self):
        expired = AttachmentFactory.create()
        recent = AttachmentFactory.create()
        sent = AttachmentFactory.create(
            turn=TurnFactory.create(status=Turn.Status.DONE),
        )
        old = timezone.now() - timedelta(seconds=PENDING_SECONDS + 1)
        Attachment.objects.filter(id__in=[expired.id, sent.id]).update(created_at=old)

        deleted = AttachmentCommandRepository().delete_expired(
            command=DeleteExpiredAttachmentsCommandDTO(pending_seconds=PENDING_SECONDS),
        )

        assert deleted.paths == (str(expired.file),)
        assert set(Attachment.objects.values_list("id", flat=True)) == {
            recent.id,
            sent.id,
        }
