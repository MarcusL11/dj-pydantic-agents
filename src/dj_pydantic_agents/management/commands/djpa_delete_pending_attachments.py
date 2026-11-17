"""Delete the pending files that expired. For a project with no Celery Beat."""

from typing import Any

from django.core.management.base import BaseCommand

from dj_pydantic_agents import entry


class Command(BaseCommand):
    help = "Delete the pending attachment files older than PENDING_ATTACHMENT_SECONDS."

    def handle(self, *args: Any, **options: Any) -> None:
        deleted = entry.delete_expired_attachments()
        self.stdout.write(f"Deleted {deleted} expired pending files.")
