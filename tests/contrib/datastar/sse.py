"""Read the Datastar events of a response body in a test."""

from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http.response import HttpResponseBase


@dataclass
class Patch:
    """One SSE event. A comment line has the kind "comment"."""

    kind: str
    selector: str = ""
    mode: str = "outer"
    elements: str = ""
    signals: str = ""
    lines: list[str] = field(default_factory=list)


async def read_patches(response: HttpResponseBase) -> list[Patch]:
    chunks = [chunk async for chunk in response.streaming_content]  # type: ignore[attr-defined]
    return parse(b"".join(chunks).decode())


def parse(body: str) -> list[Patch]:
    return [_patch(block) for block in body.split("\n\n") if block.strip()]


def _patch(block: str) -> Patch:
    if block.startswith(":"):
        return Patch(kind="comment", lines=[block])
    patch = Patch(kind="")
    elements: list[str] = []
    signals: list[str] = []
    for line in block.splitlines():
        name, _, value = line.partition(": ")
        if name == "event":
            patch.kind = value
            continue
        key, _, rest = value.partition(" ")
        if key == "selector":
            patch.selector = rest
        elif key == "mode":
            patch.mode = rest
        elif key == "elements":
            elements.append(rest)
        elif key == "signals":
            signals.append(rest)
    patch.elements = "\n".join(elements)
    patch.signals = "\n".join(signals)
    return patch
