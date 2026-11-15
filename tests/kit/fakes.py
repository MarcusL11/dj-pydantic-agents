"""Scripted models for the kit tests. They make no network call."""

from typing import TYPE_CHECKING

from pydantic_ai.messages import ModelMessage
from pydantic_ai.messages import ModelRequest
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.models.function import DeltaToolCall
from pydantic_ai.models.function import DeltaToolCalls
from pydantic_ai.models.function import FunctionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def text_model(*chunks: str) -> FunctionModel:
    """A model that streams the chunks as its reply."""

    async def stream(
        _messages: list[ModelMessage],
        _info: AgentInfo,
    ) -> AsyncIterator[str]:
        for chunk in chunks:
            yield chunk

    return FunctionModel(stream_function=stream)


def approval_model(*, tool_name: str, args_json: str, reply: str) -> FunctionModel:
    """A model that calls one tool, then replies with the tool result after it."""

    async def stream(
        messages: list[ModelMessage],
        _info: AgentInfo,
    ) -> AsyncIterator[str | DeltaToolCalls]:
        tool_return = _last_tool_return(messages)
        if tool_return is None:
            yield {
                0: DeltaToolCall(
                    name=tool_name,
                    json_args=args_json,
                    tool_call_id="call-1",
                ),
            }
        else:
            yield f"{reply} {tool_return.content}"

    return FunctionModel(stream_function=stream)


def _last_tool_return(messages: list[ModelMessage]) -> ToolReturnPart | None:
    last = messages[-1]
    if not isinstance(last, ModelRequest):
        return None
    return next((part for part in last.parts if isinstance(part, ToolReturnPart)), None)
