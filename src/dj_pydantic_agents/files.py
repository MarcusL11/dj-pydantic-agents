"""Write, read and delete the stored files of the attachments."""

import logging

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.core.files.storage import storages

logger = logging.getLogger(__name__)


class AttachmentFileStore:
    """The files of ATTACHMENT_STORAGE. The constructor opens no connection."""

    def __init__(self, *, storage_alias: str) -> None:
        self._storage_alias = storage_alias

    def save(self, *, path: str, data: bytes) -> str:
        """Write the file. Return the name that the storage used."""
        return self._storage().save(path, ContentFile(data))

    def read(self, *, path: str) -> bytes:
        with self._storage().open(path, "rb") as file:
            return file.read()

    def delete(self, *, paths: tuple[str, ...]) -> None:
        """Delete each file. Log an error and go on, because the rows are gone."""
        storage = self._storage()
        for path in paths:
            try:
                storage.delete(path)
            except Exception:
                logger.exception("The attachment file %s was not deleted.", path)

    def _storage(self) -> Storage:
        return storages[self._storage_alias]
