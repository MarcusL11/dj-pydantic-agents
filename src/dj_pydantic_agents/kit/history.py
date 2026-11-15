"""Conversation history and pending approvals to JSON data and back.

The JSON data is plain lists and dicts, ready for a JSON database column.
"""

from typing import Any

from pydantic import TypeAdapter
from pydantic_ai.messages import ModelMessage
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.tools import DeferredToolRequests

from dj_pydantic_agents.kit.events import PendingApprovalDTO

_PENDING_ADAPTER: TypeAdapter[DeferredToolRequests] = TypeAdapter(DeferredToolRequests)


def messages_to_json(messages: list[ModelMessage]) -> list[Any]:
    return ModelMessagesTypeAdapter.dump_python(messages, mode="json")


def messages_from_json(data: list[Any]) -> list[ModelMessage]:
    return ModelMessagesTypeAdapter.validate_python(data)


def pending_to_json(pending: DeferredToolRequests | None) -> dict[str, Any] | None:
    if pending is None:
        return None
    return _PENDING_ADAPTER.dump_python(pending, mode="json")


def pending_from_json(data: dict[str, Any] | None) -> DeferredToolRequests | None:
    if data is None:
        return None
    return _PENDING_ADAPTER.validate_python(data)


def describe_pending(pending: DeferredToolRequests) -> tuple[PendingApprovalDTO, ...]:
    return tuple(
        PendingApprovalDTO(
            tool_call_id=part.tool_call_id,
            tool_name=part.tool_name,
            args_json=part.args_as_json_str(),
        )
        for part in pending.approvals
    )
