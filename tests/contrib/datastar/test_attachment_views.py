from datetime import timedelta
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from dj_pydantic_agents.models import Attachment
from dj_pydantic_agents.models import Turn
from tests.contrib.datastar.sse import read_patches
from tests.factories import AttachmentFactory
from tests.factories import ConversationFactory
from tests.factories import UserFactory
from tests.fakes import FakeTaskRunner
from tests.testcases import TestCase

if TYPE_CHECKING:
    from django.contrib.auth.models import User

    from dj_pydantic_agents.models import Conversation

PDF_BYTES = b"%PDF-1.7 invoice"
PNG_BYTES = b"\x89PNG\r\n\x1a\n tiny"


class TestUploadAttachments(TestCase):
    owner: User
    conversation: Conversation

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create(is_staff=True)
        cls.conversation = ConversationFactory.create(owner=cls.owner)

    async def upload(self, *files, user=None, **extra):
        await self.async_client.aforce_login(user or self.owner)
        return await self.async_client.post(
            reverse(
                "dj_pydantic_agents:upload_attachments",
                args=[self.conversation.id],
            ),
            {"files": list(files)},
            **extra,
        )

    async def test_stores_the_files_and_shows_their_chips(self):
        response = await self.upload(
            SimpleUploadedFile("invoice.pdf", PDF_BYTES),
            SimpleUploadedFile("dial.png", PNG_BYTES),
        )

        assert response.status_code == 200  # noqa: PLR2004
        [patch] = await read_patches(response)
        assert (patch.selector, patch.mode) == ("#djpa-attachments", "replace")
        files = [file async for file in Attachment.objects.order_by("name")]
        assert [file.name for file in files] == ["dial.png", "invoice.pdf"]
        assert all(file.turn_id is None for file in files)
        with storages["default"].open(str(files[1].file)) as stored:
            assert stored.read() == PDF_BYTES
        for file in files:
            assert f'name="attachment" value="{file.id}"' in patch.elements
        assert "invoice.pdf" in patch.elements
        assert "djpa-file__thumb" in patch.elements
        assert '<span class="djpa-file__badge">PDF</span>' in patch.elements

    async def test_a_refused_file_shows_the_error_and_a_new_input(self):
        response = await self.upload(SimpleUploadedFile("tool.exe", b"MZ"))

        error, file_input = await read_patches(response)
        assert error.selector == "#djpa-attachments-error"
        assert "tool.exe is not a file type" in error.elements
        assert (file_input.selector, file_input.mode) == (
            "#djpa-attachment-input",
            "replace",
        )
        assert 'type="file"' in file_input.elements
        assert not await Attachment.objects.aexists()

    async def test_a_large_request_is_refused_before_the_files_are_read(self):
        values = {**settings.DJ_PYDANTIC_AGENTS, "ATTACHMENT_MAX_MESSAGE_BYTES": 1}
        data = PDF_BYTES + b"\0" * (2 * 1024 * 1024)

        with override_settings(DJ_PYDANTIC_AGENTS=values):
            response = await self.upload(SimpleUploadedFile("invoice.pdf", data))

        error, _input = await read_patches(response)
        assert "larger than 1 MB" in error.elements
        assert not await Attachment.objects.aexists()

    async def test_another_user_gets_not_found(self):
        other = await sync_to_async(UserFactory.create)(is_staff=True)

        response = await self.upload(SimpleUploadedFile("a.pdf", PDF_BYTES), user=other)

        assert response.status_code == 404  # noqa: PLR2004

    async def test_no_files_is_a_bad_request(self):
        await self.async_client.aforce_login(self.owner)

        response = await self.async_client.post(
            reverse(
                "dj_pydantic_agents:upload_attachments",
                args=[self.conversation.id],
            ),
        )

        assert response.status_code == 400  # noqa: PLR2004


class TestRemoveAttachment(TestCase):
    owner: User
    attachment: Attachment

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create(is_staff=True)
        cls.attachment = AttachmentFactory.create(
            conversation=ConversationFactory.create(owner=cls.owner),
            uploaded_by=cls.owner,
        )

    async def remove(self):
        await self.async_client.aforce_login(self.owner)
        return await self.async_client.post(
            reverse("dj_pydantic_agents:remove_attachment", args=[self.attachment.id]),
        )

    async def test_deletes_the_file_and_shows_the_rest(self):
        storage = storages["default"]
        name = storage.save(str(self.attachment.file), ContentFile(PDF_BYTES))
        await Attachment.objects.filter(id=self.attachment.id).aupdate(file=name)

        response = await self.remove()

        [patch] = await read_patches(response)
        assert patch.selector == "#djpa-attachments"
        assert self.attachment.id not in patch.elements
        assert not await Attachment.objects.aexists()
        assert not storage.exists(name)

    async def test_a_file_that_is_gone_loses_its_chip(self):
        await Attachment.objects.filter(id=self.attachment.id).adelete()

        response = await self.remove()

        [patch] = await read_patches(response)
        assert patch.kind == "datastar-patch-elements"
        assert patch.mode == "remove"
        assert patch.selector == f"#djpa-attachment-{self.attachment.id}"


class TestAttachmentFile(TestCase):
    owner: User
    attachment: Attachment

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create(is_staff=True)
        cls.attachment = AttachmentFactory.create(
            conversation=ConversationFactory.create(owner=cls.owner),
            name="invoice.pdf",
        )

    def setUp(self):
        storages["default"].save(str(self.attachment.file), ContentFile(PDF_BYTES))
        self.addCleanup(storages["default"].delete, str(self.attachment.file))

    def url(self):
        return reverse("dj_pydantic_agents:attachment_file", args=[self.attachment.id])

    async def test_the_owner_gets_the_bytes(self):
        await self.async_client.aforce_login(self.owner)

        response = await self.async_client.get(self.url())

        assert response.status_code == 200  # noqa: PLR2004
        assert response.content == PDF_BYTES
        assert response["Content-Type"] == "application/pdf"
        assert response["Content-Disposition"] == 'inline; filename="invoice.pdf"'
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["Cache-Control"] == "private, no-store"

    async def test_a_spreadsheet_downloads(self):
        await Attachment.objects.filter(id=self.attachment.id).aupdate(
            name="stock.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        await self.async_client.aforce_login(self.owner)

        response = await self.async_client.get(self.url())

        assert response["Content-Disposition"] == 'attachment; filename="stock.xlsx"'

    async def test_another_user_gets_not_found(self):
        await self.async_client.aforce_login(
            await sync_to_async(UserFactory.create)(is_staff=True),
        )

        response = await self.async_client.get(self.url())

        assert response.status_code == 404  # noqa: PLR2004

    async def test_a_post_is_not_allowed(self):
        await self.async_client.aforce_login(self.owner)

        response = await self.async_client.post(self.url())

        assert response.status_code == 405  # noqa: PLR2004


class TestSendWithAttachments(TestCase):
    owner: User
    conversation: Conversation

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create(is_staff=True)
        cls.conversation = ConversationFactory.create(owner=cls.owner)

    def setUp(self):
        FakeTaskRunner.reset()

    async def send(self, *attachment_ids):
        await self.async_client.aforce_login(self.owner)
        return await self.async_client.post(
            reverse("dj_pydantic_agents:send_message", args=[self.conversation.id]),
            {"prompt": "Read this", "attachment": list(attachment_ids)},
        )

    async def test_the_message_line_shows_its_files(self):
        file = await sync_to_async(AttachmentFactory.create)(
            conversation=self.conversation,
            uploaded_by=self.owner,
            name="invoice.pdf",
        )

        response = await self.send(file.id)

        line, _reply, _form = await read_patches(response)
        assert "Read this" in line.elements
        assert "invoice.pdf" in line.elements
        attachment_url = reverse("dj_pydantic_agents:attachment_file", args=[file.id])
        assert f'href="{attachment_url}"' in line.elements
        turn = await Turn.objects.aget(conversation_id=self.conversation.id)
        await file.arefresh_from_db()
        assert file.turn_id == turn.id

    async def test_an_expired_file_shows_an_error_and_starts_no_turn(self):
        file = await sync_to_async(AttachmentFactory.create)(
            conversation=self.conversation,
            uploaded_by=self.owner,
        )
        await Attachment.objects.filter(id=file.id).aupdate(
            created_at=timezone.now() - timedelta(days=1),
        )

        response = await self.send(file.id)

        [error] = await read_patches(response)
        assert error.selector == "#djpa-attachments-error"
        assert "Attach it again" in error.elements
        assert not await Turn.objects.aexists()
        assert FakeTaskRunner.turn_ids == []
