"""Template filters of the package templates. Load them with {% load djpa %}."""

from django import template
from django.utils.safestring import SafeString
from django.utils.safestring import mark_safe

from dj_pydantic_agents.composition import build_reply_sanitizer

register = template.Library()


@register.filter
def djpa_reply_html(text: str) -> SafeString:
    """The Markdown of a reply as HTML, after the SANITIZER removes unsafe parts."""
    return mark_safe(build_reply_sanitizer().to_html(text=text))  # noqa: S308
