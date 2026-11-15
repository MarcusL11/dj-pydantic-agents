"""A scripted model and a thread task runner for the demo project.

The model reads the last user prompt:

- "mail": it calls send_mail, which waits for an approval.
- "slow": it streams one word each second for 90 seconds. The stream view
  stops each stream after 60 seconds, so the page must open a new one.
- else: it streams a short Markdown reply.
"""

import asyncio
import threading
from itertools import count
from typing import TYPE_CHECKING

from django.db import connections
from django.db import transaction
from pydantic_ai.messages import ModelRequest
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.messages import UserPromptPart
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.models.function import DeltaToolCall
from pydantic_ai.models.function import DeltaToolCalls
from pydantic_ai.models.function import FunctionModel

from dj_pydantic_agents import entry

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models import Model

    from dj_pydantic_agents.dtos.turn_commands import UserId
    from dj_pydantic_agents.kit.roles import ModelRole

SLOW_SECONDS = 90
WORD_SECONDS = 0.05
# The reply after an approval is slow, so that the page shows it while it streams.
RESUME_WORD_SECONDS = 0.5
REPLY = (
    "Here is a **Markdown** reply, with a list:\n\n"
    "- one item\n- a second item\n\n"
    "And some `code`:\n\n```python\nprint('hello')\n```\n"
)
_call_numbers = count(1)


async def _stream(
    messages: list[ModelMessage],
    _info: AgentInfo,
) -> AsyncIterator[str | DeltaToolCalls]:
    tool_return = _last_tool_return(messages)
    prompt = _last_prompt(messages)
    if tool_return is not None:
        for word in f"The tool said: {tool_return.content}. Done.".split(" "):
            await asyncio.sleep(RESUME_WORD_SECONDS)
            yield f"{word} "
    elif "mail" in prompt:
        yield "I will send the mail now."
        yield {
            0: DeltaToolCall(
                name="send_mail",
                json_args='{"to": "ada@example.com"}',
                tool_call_id=f"demo-call-{next(_call_numbers)}",
            ),
        }
    elif "slow" in prompt:
        for second in range(1, SLOW_SECONDS + 1):
            await asyncio.sleep(1)
            yield f"{second} "
    else:
        for word in REPLY.split(" "):
            await asyncio.sleep(WORD_SECONDS)
            yield f"{word} "


def _last_prompt(messages: list[ModelMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    return part.content
    return ""


def _last_tool_return(messages: list[ModelMessage]) -> ToolReturnPart | None:
    last = messages[-1]
    if not isinstance(last, ModelRequest):
        return None
    return next((part for part in last.parts if isinstance(part, ToolReturnPart)), None)


class DemoModelFactory:
    def build(self, *, role: ModelRole, user_id: UserId) -> Model:
        return FunctionModel(stream_function=_stream)


class ThreadTaskRunner:
    """Run each turn in a thread of the server process, after the commit."""

    def enqueue(self, *, turn_id: str) -> None:
        transaction.on_commit(lambda: _start_thread(turn_id))


def _start_thread(turn_id: str) -> None:
    threading.Thread(target=_run_turn, args=(turn_id,), daemon=True).start()


def _run_turn(turn_id: str) -> None:
    try:
        entry.run_turn(turn_id)
    finally:
        connections.close_all()
