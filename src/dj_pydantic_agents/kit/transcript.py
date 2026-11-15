"""The lines of a conversation, as a chat page shows them."""

from typing import TYPE_CHECKING
from typing import Literal

from pydantic_ai.messages import TextPart
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.messages import UserPromptPart

from dj_pydantic_agents.kit.dtos import InternalDTO

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.messages import ModelRequestPart
    from pydantic_ai.messages import ModelResponsePart

# The text of a user prompt part that holds no text, for example an image.
NON_TEXT_PROMPT = "[attachment]"


class TranscriptLineDTO(InternalDTO):
    kind: Literal["user", "assistant", "tool_call", "tool_result"]
    text: str
    tool_name: str | None = None


def transcript_lines(messages: Sequence[ModelMessage]) -> tuple[TranscriptLineDTO, ...]:
    """Map the history to lines. Skip system, instruction, thinking and retry parts."""
    return tuple(
        line
        for message in messages
        for part in message.parts
        if (line := _line(part)) is not None
    )


def _line(part: ModelRequestPart | ModelResponsePart) -> TranscriptLineDTO | None:
    match part:
        case UserPromptPart(content=content):
            text = content if isinstance(content, str) else _prompt_text(content)
            return TranscriptLineDTO(kind="user", text=text)
        case TextPart(content=text) if text:
            return TranscriptLineDTO(kind="assistant", text=text)
        case ToolCallPart(tool_name=tool_name):
            return TranscriptLineDTO(
                kind="tool_call",
                text=part.args_as_json_str(),
                tool_name=tool_name,
            )
        case ToolReturnPart(tool_name=tool_name):
            return TranscriptLineDTO(
                kind="tool_result",
                text=part.model_response_str(),
                tool_name=tool_name,
            )
        case _:
            return None


def _prompt_text(content: Sequence[object]) -> str:
    texts = [item for item in content if isinstance(item, str)]
    return "\n".join(texts) if texts else NON_TEXT_PROMPT
