"""Template filters of the package templates. Load them with {% load djpa %}."""

from typing import TYPE_CHECKING

from django import template
from django.utils.safestring import SafeString
from django.utils.safestring import mark_safe

from dj_pydantic_agents.composition import build_reply_sanitizer
from dj_pydantic_agents.conf import load_settings
from dj_pydantic_agents.dtos.attachments import AttachmentProjectionDTO
from dj_pydantic_agents.kit.attachments import PromptFileRefDTO
from dj_pydantic_agents.kit.file_checks import SUFFIXES
from dj_pydantic_agents.kit.file_checks import accept_value

if TYPE_CHECKING:
    from collections.abc import Sequence

register = template.Library()

# A file of the transcript or of the message form.
type FileView = PromptFileRefDTO | AttachmentProjectionDTO


@register.filter
def djpa_reply_html(text: str) -> SafeString:
    """The Markdown of a reply as HTML, after the SANITIZER removes unsafe parts."""
    return mark_safe(build_reply_sanitizer().to_html(text=text))  # noqa: S308


@register.simple_tag
def djpa_attachment_accept() -> str:
    """The accept value of the file input. Empty when the chat takes no files."""
    return accept_value(tuple(load_settings().attachment_types))


@register.filter
def djpa_images(files: Sequence[FileView]) -> list[FileView]:
    """The images of a list of files, in their order."""
    return [file for file in files if file.is_image]


@register.filter
def djpa_documents(files: Sequence[FileView]) -> list[FileView]:
    """The files that are not images, in their order."""
    return [file for file in files if not file.is_image]


@register.filter
def djpa_file_badge(media_type: str) -> str:
    """The short type of a file for its badge, for example PDF or DOCX."""
    suffix = SUFFIXES.get(media_type)
    return suffix.removeprefix(".").upper() if suffix else "FILE"
