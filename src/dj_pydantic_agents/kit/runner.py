"""Build the agent of a spec and run one turn."""

from collections.abc import AsyncIterable
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai import RunContext
from pydantic_ai.messages import repair_messages
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.tools import DeferredToolResults
from pydantic_ai.tools import ToolDenied

from dj_pydantic_agents.kit.events import TurnEventDTO
from dj_pydantic_agents.kit.events import to_turn_event

if TYPE_CHECKING:
    from pydantic_ai.agent import EventStreamHandler
    from pydantic_ai.messages import AgentStreamEvent
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models import Model
    from pydantic_ai.usage import RunUsage
    from pydantic_ai.usage import UsageLimits

    from dj_pydantic_agents.kit.specs import AgentSpec

type EventSink = Callable[[TurnEventDTO], None]

DENIED_MESSAGE = "The user denied this tool call."


@dataclass(frozen=True, kw_only=True)
class TurnOutcome:
    """The result of one turn. The caller saves it."""

    new_messages: tuple[ModelMessage, ...]
    usage: RunUsage
    reply_text: str | None
    pending_approvals: DeferredToolRequests | None


class TurnRunner:
    """Run one turn of an agent. It loads and saves nothing."""

    def run(  # noqa: PLR0913
        self,
        *,
        spec: AgentSpec,
        model: Model,
        history: list[ModelMessage],
        prompt: str | None,
        pending: DeferredToolRequests | None,
        decisions: Mapping[str, bool] | None,
        deps: object,
        on_event: EventSink,
        usage_limits: UsageLimits | None = None,
    ) -> TurnOutcome:
        """Run a prompt, or continue a turn with the approval decisions.

        Give a prompt, or give the pending approvals with their decisions.
        """
        approval_results = _approval_results(pending=pending, decisions=decisions)
        if (prompt is None) == (approval_results is None):
            msg = "Give a prompt, or give the pending approvals with their decisions."
            raise ValueError(msg)

        if prompt is not None:
            # A failed resume can leave a tool call with no result. Pydantic AI
            # refuses a new prompt after it, so close such calls first.
            history = repair_messages(history)
        agent = _build_agent(spec=spec, model=model)
        # message_history, not conversation: with conversation, the usage limits
        # count the requests of the whole conversation.
        result = agent.run_sync(
            prompt,
            message_history=history,
            deferred_tool_results=approval_results,
            deps=deps,
            usage_limits=usage_limits,
            event_stream_handler=_event_handler(on_event),
        )
        output = result.output
        return TurnOutcome(
            new_messages=tuple(result.new_messages()),
            usage=result.usage,
            reply_text=output if isinstance(output, str) else None,
            pending_approvals=output
            if isinstance(output, DeferredToolRequests)
            else None,
        )


def _build_agent(
    *,
    spec: AgentSpec,
    model: Model,
) -> Agent[object, str | DeferredToolRequests]:
    return Agent(
        model,
        name=spec.name,
        instructions=spec.instructions,
        deps_type=spec.deps_type,
        output_type=[str, DeferredToolRequests],
        toolsets=spec.toolsets,
        capabilities=list(spec.capabilities),
    )


def _approval_results(
    *,
    pending: DeferredToolRequests | None,
    decisions: Mapping[str, bool] | None,
) -> DeferredToolResults | None:
    if pending is None or decisions is None:
        return None
    # The decisions can also hold the calls of an earlier stop of the turn.
    # Pydantic AI refuses a decision for a call that is not pending.
    pending_ids = {call.tool_call_id for call in pending.approvals}
    return pending.build_results(
        approvals={
            tool_call_id: True if approved else ToolDenied(message=DENIED_MESSAGE)
            for tool_call_id, approved in decisions.items()
            if tool_call_id in pending_ids
        },
    )


def _event_handler(on_event: EventSink) -> EventStreamHandler[object]:
    async def handle(
        _ctx: RunContext[object],
        events: AsyncIterable[AgentStreamEvent],
    ) -> None:
        async for event in events:
            turn_event = to_turn_event(event)
            if turn_event is not None:
                on_event(turn_event)

    return handle
