"""Read the state of the message form in rendered HTML."""

import re

# The textarea tag, up to its end. Its attributes hold no ">".
_TEXTAREA = re.compile(r"<textarea\b[^>]*>")


def form_is_closed(html: str) -> bool:
    """A closed form has a disabled textarea.

    Other words with "disabled" in the form, for example in an expression,
    do not count.
    """
    match = _TEXTAREA.search(html)
    assert match is not None, "The HTML has no textarea."
    return re.search(r"\sdisabled\b", match.group()) is not None
