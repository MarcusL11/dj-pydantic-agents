from datetime import timedelta
from io import StringIO

from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.management import call_command
from django.utils import timezone

from dj_pydantic_agents.models import Attachment
from tests.factories import AttachmentFactory
from tests.testcases import TestCase


class TestDeletePendingAttachmentsCommand(TestCase):
    def test_deletes_the_expired_rows_and_their_files(self):
        storage = storages["default"]
        expired = AttachmentFactory.create()
        name = storage.save(str(expired.file), ContentFile(b"%PDF-1.7"))
        Attachment.objects.filter(id=expired.id).update(
            file=name,
            created_at=timezone.now() - timedelta(days=1),
        )
        recent = AttachmentFactory.create()
        out = StringIO()

        call_command("djpa_delete_pending_attachments", stdout=out)

        assert out.getvalue() == "Deleted 1 expired pending files.\n"
        assert list(Attachment.objects.values_list("id", flat=True)) == [recent.id]
        assert not storage.exists(name)
