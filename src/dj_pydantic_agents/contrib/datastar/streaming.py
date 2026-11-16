"""Make the text of a streaming reply move smoothly.

The model sends text in uneven parts. TextReveal shows it in small, even steps.
close_open_markdown closes the Markdown of a reply that is not complete, so
that the formatting does not change when the closing mark comes.
number_blocks gives each top-level element an ID, so that a patch can change
only the block that grows.
"""

import math
import re
from html.parser import HTMLParser

# Each step shows this part of the waiting text, to the end of a word. The
# waiting text grows when the model sends faster, so the steps grow too.
REVEAL_FRACTION = 0.25

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_WHITESPACE = re.compile(r"\s")
_TABLE_ROW = re.compile(r"^\s*\|")
_TABLE_DELIMITER = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
_TAG_NAME = re.compile(r"<[^\s/>]+")
_VOID_TAGS = frozenset({"area", "br", "col", "embed", "hr", "img", "input", "wbr"})


class TextReveal:
    """The text of a reply: the shown part and the part that waits."""

    def __init__(self) -> None:
        self.shown = ""
        self._waiting = ""

    @property
    def is_waiting(self) -> bool:
        return bool(self._waiting)

    def add(self, text: str) -> None:
        self._waiting += text

    def step(self) -> None:
        """Show the next part of the waiting text, to the end of a word."""
        size = max(1, math.ceil(len(self._waiting) * REVEAL_FRACTION))
        space = _WHITESPACE.search(self._waiting, size - 1)
        end = space.end() if space else len(self._waiting)
        self.shown += self._waiting[:end]
        self._waiting = self._waiting[end:]

    def show_all(self) -> None:
        self.shown += self._waiting
        self._waiting = ""

    def clear(self) -> None:
        self.shown = ""
        self._waiting = ""


def close_open_markdown(text: str) -> str:
    """Close the open Markdown at the end of a reply that is not complete.

    Close an open code fence, an open inline code span and open bold text.
    Hold back a table until its delimiter row comes. The result is only for
    the display. The full reply converts as it is.
    """
    text = text.rstrip()
    fence = _open_fence(text)
    if fence is not None:
        return f"{text}\n{fence}"
    head, separator, block = text.rpartition("\n\n")
    if _is_table_without_delimiter(block):
        return head
    if block.count("`") % 2:
        block += "`"
    if _INLINE_CODE.sub("", block).count("**") % 2:
        block += "**"
    return head + separator + block


def number_blocks(html: str, *, id_prefix: str) -> tuple[str, ...] | None:
    """Split HTML into its top-level elements, each with the ID id_prefix + index.

    Return None when the HTML has text outside an element, because text can
    have no ID.
    """
    splitter = _BlockSplitter(html)
    if splitter.has_loose_text:
        return None
    return tuple(
        f'{html[start:name_end]} id="{id_prefix}{index}"{html[name_end:end]}'
        for index, (start, name_end, end) in enumerate(splitter.blocks)
    )


def _open_fence(text: str) -> str | None:
    fence: str | None = None
    for line in text.split("\n"):
        match = _FENCE.match(line)
        if match is None:
            continue
        marker = match.group(1)
        if fence is None:
            fence = marker
        elif (
            line.strip() == marker
            and marker[0] == fence[0]
            and len(marker) >= len(fence)
        ):
            fence = None
    return fence


def _is_table_without_delimiter(block: str) -> bool:
    lines = block.split("\n")
    return bool(_TABLE_ROW.match(lines[0])) and not any(
        _TABLE_DELIMITER.match(line) for line in lines[1:]
    )


class _BlockSplitter(HTMLParser):
    """Find the start, the end of the tag name and the end of each top-level element."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=False)
        self.blocks: list[tuple[int, int, int]] = []
        self.has_loose_text = False
        self._html = html
        self._line_starts = [0] + [
            index + 1 for index, char in enumerate(html) if char == "\n"
        ]
        self._depth = 0
        self._start = 0
        self.feed(html)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID_TAGS:
            self.handle_startendtag(tag, attrs)
            return
        if self._depth == 0:
            self._start = self._offset()
        self._depth += 1

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if self._depth == 0:
            self._start = self._offset()
            self._add_block(end=self._start + len(self.get_starttag_text() or ""))

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_TAGS:
            return
        self._depth -= 1
        if self._depth == 0:
            self._add_block(end=self._html.index(">", self._offset()) + 1)

    def handle_data(self, data: str) -> None:
        if self._depth == 0 and data.strip():
            self.has_loose_text = True

    def handle_entityref(self, name: str) -> None:
        if self._depth == 0:
            self.has_loose_text = True

    def handle_charref(self, name: str) -> None:
        if self._depth == 0:
            self.has_loose_text = True

    def _offset(self) -> int:
        line, column = self.getpos()
        return self._line_starts[line - 1] + column

    def _add_block(self, *, end: int) -> None:
        name = _TAG_NAME.match(self._html, self._start)
        if name is None:
            self.has_loose_text = True
            return
        self.blocks.append((self._start, name.end(), end))
