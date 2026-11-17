"""The files of a user prompt, and their bytes in the stored history.

A prompt with files is a list: the text, then a label and a BinaryContent for
each file. The identifier of the BinaryContent is the attachment ID.

The stored history keeps each file as a BinaryContent with no data. Before a
run, the bytes of the latest turns go back in. An older file stays out, and
its label tells the model that the file is not in the request.
"""

from dataclasses import dataclass
from dataclasses import replace
from typing import TYPE_CHECKING
from typing import TypeIs

from pydantic_ai.messages import BinaryContent
from pydantic_ai.messages import ModelRequest
from pydantic_ai.messages import UserPromptPart

from dj_pydantic_agents.kit.dtos import InternalDTO

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Collection
    from collections.abc import Mapping
    from collections.abc import Sequence

    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.messages import UserContent

LABEL_PREFIX = "Attached file: "
EARLIER_NOTE = " (from an earlier message. The file is not in this request.)"


@dataclass(frozen=True, kw_only=True)
class PromptFile:
    """One file for the prompt. A dataclass, not a DTO, because it holds the bytes."""

    attachment_id: str
    name: str
    media_type: str
    data: bytes


class PromptFileRefDTO(InternalDTO):
    """A file of a user prompt, as the transcript shows it."""

    attachment_id: str
    name: str
    media_type: str
    is_image: bool
    # The history keeps no size. The page query adds it from the row of the file.
    size: int | None = None


def user_prompt(*, text: str, files: Sequence[PromptFile]) -> str | list[UserContent]:
    """The text alone, or the text with a label and the bytes of each file."""
    if not files:
        return text
    content: list[UserContent] = [text]
    for file in files:
        content += [
            f"{LABEL_PREFIX}{file.name}",
            BinaryContent(
                data=file.data,
                media_type=file.media_type,
                identifier=file.attachment_id,
            ),
        ]
    return content


def without_file_data(
    messages: Sequence[ModelMessage],
    *,
    attachment_ids: Collection[str],
) -> list[ModelMessage]:
    """Remove the bytes of these attachments. Keep the type and the identifier."""

    def empty(content: list[UserContent]) -> list[UserContent]:
        return [
            _with_data(item, b"")
            if _is_file(item) and item.identifier in attachment_ids
            else item
            for item in content
        ]

    return _map_prompts(messages, empty)


def with_file_data(
    messages: Sequence[ModelMessage],
    *,
    data: Mapping[str, bytes],
) -> list[ModelMessage]:
    """Put the bytes back. A file with no bytes in data goes, and its label changes."""

    def fill(content: list[UserContent]) -> list[UserContent]:
        filled: list[UserContent] = []
        for item in content:
            if not (_is_file(item) and not item.data):
                filled.append(item)
            elif item.identifier in data:
                filled.append(_with_data(item, data[item.identifier]))
            elif filled and _is_label(filled[-1]):
                filled[-1] = f"{filled[-1]}{EARLIER_NOTE}"
        return filled

    return _map_prompts(messages, fill)


def split_prompt(
    content: Sequence[UserContent],
) -> tuple[str, tuple[PromptFileRefDTO, ...]]:
    """The text of the user and the files of a prompt list.

    A file is a BinaryContent after a label. Other items that are not text,
    for example an image of other code, do not show.
    """
    texts: list[str] = []
    files: list[PromptFileRefDTO] = []
    for index, item in enumerate(content):
        if isinstance(item, str):
            if not (_is_label(item) and _is_file(_item_at(content, index + 1))):
                texts.append(item)
        elif _is_file(item) and _is_label(_item_at(content, index - 1)):
            label = str(_item_at(content, index - 1))
            files.append(
                PromptFileRefDTO(
                    attachment_id=item.identifier,
                    name=label.removeprefix(LABEL_PREFIX).removesuffix(EARLIER_NOTE),
                    media_type=item.media_type,
                    is_image=item.is_image,
                ),
            )
    return "\n".join(texts), tuple(files)


def _map_prompts(
    messages: Sequence[ModelMessage],
    change: Callable[[list[UserContent]], list[UserContent]],
) -> list[ModelMessage]:
    """Copy the messages. Change the content list of each user prompt part."""
    return [
        replace(
            message,
            parts=[
                replace(part, content=change(list(part.content)))
                if isinstance(part, UserPromptPart)
                and not isinstance(part.content, str)
                else part
                for part in message.parts
            ],
        )
        if isinstance(message, ModelRequest)
        else message
        for message in messages
    ]


def _with_data(item: BinaryContent, data: bytes) -> BinaryContent:
    # Not dataclasses.replace(): it loses the identifier.
    return BinaryContent(
        data=data,
        media_type=item.media_type,
        identifier=item.identifier,
        vendor_metadata=item.vendor_metadata,
    )


def _is_file(item: object) -> TypeIs[BinaryContent]:
    return isinstance(item, BinaryContent)


def _is_label(item: object) -> bool:
    return isinstance(item, str) and item.startswith(LABEL_PREFIX)


def _item_at(content: Sequence[UserContent], index: int) -> object:
    return content[index] if 0 <= index < len(content) else None
