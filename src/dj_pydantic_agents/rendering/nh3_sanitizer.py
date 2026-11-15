"""Turn the Markdown of an agent reply into HTML that a page can show.

The model writes the reply, so the HTML is untrusted. nh3 removes each tag,
attribute and link scheme that is not in the lists below.
"""

import markdown
import nh3

MARKDOWN_EXTENSIONS = ("fenced_code", "tables")

ALLOWED_TAGS = frozenset(
    {
        "a",
        "blockquote",
        "br",
        "code",
        "del",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "li",
        "ol",
        "p",
        "pre",
        "strong",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "ul",
    },
)
ALLOWED_ATTRIBUTES = {"a": frozenset({"href", "title"})}
URL_SCHEMES = frozenset({"http", "https", "mailto"})
LINK_REL = "noopener noreferrer"


class Nh3Sanitizer:
    def to_html(self, *, text: str) -> str:
        html = markdown.markdown(text, extensions=list(MARKDOWN_EXTENSIONS))
        return nh3.clean(
            html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            url_schemes=URL_SCHEMES,
            link_rel=LINK_REL,
        )
