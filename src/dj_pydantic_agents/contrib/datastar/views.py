"""The send, approve and stream views. Each view returns Datastar patches.

The project writes each full page. These views only change parts of it.
"""

import asyncio
import time
from typing import TYPE_CHECKING

from datastar_py.consts import ElementPatchMode
from datastar_py.django import DatastarResponse
from datastar_py.sse import DatastarEvent
from datastar_py.sse import ServerSentEventGenerator as SSE  # noqa: N814
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST
from pydantic import ValidationError

from dj_pydantic_agents.composition import build_conversation_command_service
from dj_pydantic_agents.composition import build_event_transport
from dj_pydantic_agents.composition import build_reply_sanitizer
from dj_pydantic_agents.contrib.datastar.dtos import ApprovalDecisionPayloadDTO
from dj_pydantic_agents.contrib.datastar.dtos import SendMessagePayloadDTO
from dj_pydantic_agents.contrib.datastar.rendering import render_approval_actions
from dj_pydantic_agents.contrib.datastar.rendering import render_message_form
from dj_pydantic_agents.contrib.datastar.rendering import render_reply
from dj_pydantic_agents.contrib.datastar.rendering import render_reply_text
from dj_pydantic_agents.contrib.datastar.rendering import render_run_end
from dj_pydantic_agents.contrib.datastar.rendering import render_transcript_line
from dj_pydantic_agents.contrib.datastar.rendering import reply_id
from dj_pydantic_agents.contrib.datastar.rendering import reply_text_id
from dj_pydantic_agents.db import database_sync_to_async
from dj_pydantic_agents.dtos.turn_commands import DecideApprovalCommandDTO
from dj_pydantic_agents.dtos.turn_commands import StartTurnCommandDTO
from dj_pydantic_agents.dtos.turn_streams import OpenTurnStreamCommandDTO
from dj_pydantic_agents.errors import AgentAccessDenied
from dj_pydantic_agents.errors import AgentNotFound
from dj_pydantic_agents.errors import ApprovalNotPending
from dj_pydantic_agents.errors import ConversationNotFound
from dj_pydantic_agents.errors import DjPydanticAgentsError
from dj_pydantic_agents.errors import TurnInProgress
from dj_pydantic_agents.errors import TurnNotQueued
from dj_pydantic_agents.kit.events import START_EVENT_ID
from dj_pydantic_agents.kit.events import ApprovalRequestedEventDTO
from dj_pydantic_agents.kit.events import TextDeltaEventDTO
from dj_pydantic_agents.kit.events import TurnDoneEventDTO
from dj_pydantic_agents.kit.events import TurnFailedEventDTO

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from collections.abc import Iterator

    from django.http import HttpRequest
    from django.http.response import HttpResponseBase

    from dj_pydantic_agents.dtos.conversation_queries import ApprovalProjectionDTO
    from dj_pydantic_agents.dtos.turn_commands import ApprovalDecidedResultDTO
    from dj_pydantic_agents.dtos.turn_commands import TurnStartedResultDTO
    from dj_pydantic_agents.dtos.turn_streams import TurnSnapshotProjectionDTO
    from dj_pydantic_agents.extensions import EventTransport
    from dj_pydantic_agents.extensions import ReplySanitizer
    from dj_pydantic_agents.kit.events import StreamedTurnEventDTO
    from dj_pydantic_agents.kit.events import TurnEventDTO

# A stream lives this long at most. Then the page opens a new stream, and the
# new stream reads a new snapshot.
STREAM_SECONDS = 60
# The signal of the page that opens a new stream when its value changes.
STREAM_SIGNAL = "_djpaStream"
TRANSCRIPT_SELECTOR = "#djpa-transcript"
KEEP_ALIVE = DatastarEvent(": keep-alive\n\n")

_ERROR_STATUSES: tuple[tuple[type[DjPydanticAgentsError], int], ...] = (
    (ConversationNotFound, 404),
    (AgentNotFound, 404),
    (AgentAccessDenied, 403),
    (TurnInProgress, 409),
    (ApprovalNotPending, 409),
)
_HANDLED_ERRORS = tuple(error_type for error_type, _ in _ERROR_STATUSES)


@require_POST
async def send_message(request: HttpRequest, conversation_id: str) -> HttpResponseBase:
    """Start a turn. Show the message, a reply that streams, and a closed form."""
    user = await request.auser()
    if not user.is_authenticated:
        return HttpResponse(status=403)
    try:
        payload = SendMessagePayloadDTO(prompt=request.POST.get("prompt", ""))
    except ValidationError:
        return HttpResponse(status=400)
    command = StartTurnCommandDTO(
        conversation_id=conversation_id,
        user_id=user.pk,
        prompt=payload.prompt,
    )
    csrf_token = get_token(request)
    message = _append(render_transcript_line(kind="user", text=payload.prompt))
    try:
        started = await database_sync_to_async(_start_turn)(command)
    except TurnNotQueued as error:
        return _patches(message, *_failed_turn(error, csrf_token))
    except _HANDLED_ERRORS as error:
        return _error_response(error)
    return _patches(
        message,
        _append(render_reply(turn_id=started.turn_id)),
        _form(conversation_id=conversation_id, is_closed=True, csrf_token=csrf_token),
    )


@require_POST
async def decide_approval(request: HttpRequest, approval_id: str) -> HttpResponseBase:
    """Record a decision. After the last one, show a reply that streams."""
    user = await request.auser()
    if not user.is_authenticated:
        return HttpResponse(status=403)
    try:
        payload = ApprovalDecisionPayloadDTO.model_validate(
            {"approved": request.POST.get("approved")},
        )
    except ValidationError:
        return HttpResponse(status=400)
    command = DecideApprovalCommandDTO(
        approval_id=approval_id,
        user_id=user.pk,
        approved=payload.approved,
    )
    decision = SSE.patch_elements(
        render_approval_actions(
            approval_id=approval_id,
            decision="approved" if payload.approved else "denied",
        ),
    )
    try:
        decided = await database_sync_to_async(_decide_approval)(command)
    except TurnNotQueued as error:
        return _patches(decision, *_failed_turn(error, get_token(request)))
    except _HANDLED_ERRORS as error:
        return _error_response(error)
    if not decided.requeued:
        return _patches(decision)
    return _patches(decision, _append(render_reply(turn_id=decided.turn_id)))


@require_GET
async def stream_turn(request: HttpRequest, turn_id: str) -> HttpResponseBase:
    """Stream the reply of a turn. Read the database one time, then only events."""
    user = await request.auser()
    if not user.is_authenticated:
        return HttpResponse(status=403)
    command = OpenTurnStreamCommandDTO(turn_id=turn_id, user_id=user.pk)
    try:
        snapshot = await database_sync_to_async(_open_turn_stream)(command)
    except _HANDLED_ERRORS as error:
        return _error_response(error)
    stream = _TurnStream(
        snapshot=snapshot,
        csrf_token=get_token(request),
        transport=build_event_transport(),
        sanitizer=build_reply_sanitizer(),
    )
    return DatastarResponse(stream.events())


class _TurnStream:
    """The events of one stream. It holds no model and no database connection."""

    def __init__(
        self,
        *,
        snapshot: TurnSnapshotProjectionDTO,
        csrf_token: str,
        transport: EventTransport,
        sanitizer: ReplySanitizer,
    ) -> None:
        self._snapshot = snapshot
        self._csrf_token = csrf_token
        self._transport = transport
        self._sanitizer = sanitizer
        self._text = ""
        self._deadline = 0.0

    async def events(self) -> AsyncGenerator[DatastarEvent]:
        snapshot = self._snapshot
        if not snapshot.is_streaming:
            for event in self._run_end(
                reply_text=snapshot.reply_text,
                approvals=snapshot.approvals,
                error_code=snapshot.error_code,
            ):
                yield event
            return
        self._deadline = asyncio.get_running_loop().time() + STREAM_SECONDS
        try:
            async for event in self._turn_events():
                yield event
        except TimeoutError:
            yield _reconnect()

    async def _turn_events(self) -> AsyncGenerator[DatastarEvent]:
        """Read the events of the current run.

        An earlier stop of the turn is a final event too, so the transport
        stops after it. Then the stream reads again after its event ID.
        """
        after_id: str | None = START_EVENT_ID
        while after_id is not None:
            reader = self._transport.read(
                turn_id=self._snapshot.turn_id,
                after_id=after_id,
            )
            after_id = None
            try:
                async for streamed in self._until_deadline(reader):
                    if streamed is None:
                        yield KEEP_ALIVE
                    elif self._is_earlier_stop(streamed.event):
                        self._text = ""
                        after_id = streamed.event_id
                    else:
                        for event in self._patches_for(streamed.event):
                            yield event
            finally:
                await reader.aclose()

    async def _until_deadline(
        self,
        reader: AsyncGenerator[StreamedTurnEventDTO | None],
    ) -> AsyncGenerator[StreamedTurnEventDTO | None]:
        """Yield from the reader. Raise TimeoutError at the deadline.

        The timeout is around the read only, not around a yield. So the
        cancel of the timeout cannot reach the code that sends the response.
        """
        while True:
            async with asyncio.timeout_at(self._deadline):
                try:
                    streamed = await anext(reader)
                except StopAsyncIteration:
                    return
            yield streamed

    def _is_earlier_stop(self, event: TurnEventDTO) -> bool:
        """An approval stop with only decided tool calls is of an earlier run."""
        decided = self._snapshot.decided_tool_call_ids
        return isinstance(event, ApprovalRequestedEventDTO) and all(
            approval.tool_call_id in decided for approval in event.approvals
        )

    def _patches_for(self, event: TurnEventDTO) -> Iterator[DatastarEvent]:
        match event:
            case TextDeltaEventDTO(text=text):
                self._text += text
                yield SSE.patch_elements(
                    render_reply_text(text=self._text, sanitizer=self._sanitizer),
                    selector=f"#{reply_text_id(self._snapshot.turn_id)}",
                    mode=ElementPatchMode.INNER,
                )
            case TurnDoneEventDTO(text=text):
                yield from self._run_end(reply_text=text)
            case TurnFailedEventDTO(error_code=error_code):
                yield from self._run_end(error_code=error_code)
            case ApprovalRequestedEventDTO():
                # The event has no approval IDs for the buttons. The next
                # stream reads them with its snapshot.
                yield _reconnect()
            case _:
                pass

    def _run_end(
        self,
        *,
        reply_text: str = "",
        approvals: tuple[ApprovalProjectionDTO, ...] = (),
        error_code: str = "",
    ) -> Iterator[DatastarEvent]:
        """Put the end of the run in the place of the reply, then set the form."""
        yield SSE.patch_elements(
            render_run_end(
                reply_text=reply_text,
                approvals=approvals,
                error_code=error_code,
                csrf_token=self._csrf_token,
            ),
            selector=f"#{reply_id(self._snapshot.turn_id)}",
            mode=ElementPatchMode.REPLACE,
        )
        yield _form(
            conversation_id=self._snapshot.conversation_id,
            is_closed=bool(approvals),
            csrf_token=self._csrf_token,
        )


def _start_turn(command: StartTurnCommandDTO) -> TurnStartedResultDTO:
    return build_conversation_command_service().start_turn(command=command)


def _decide_approval(command: DecideApprovalCommandDTO) -> ApprovalDecidedResultDTO:
    return build_conversation_command_service().decide_approval(command=command)


def _open_turn_stream(command: OpenTurnStreamCommandDTO) -> TurnSnapshotProjectionDTO:
    return build_conversation_command_service().open_turn_stream(command=command)


def _failed_turn(
    error: TurnNotQueued,
    csrf_token: str,
) -> tuple[DatastarEvent, DatastarEvent]:
    """The error line and an open form, so that the user can send again."""
    return (
        _append(render_run_end(error_code=error.error_code, csrf_token=csrf_token)),
        _form(
            conversation_id=error.conversation_id,
            is_closed=False,
            csrf_token=csrf_token,
        ),
    )


def _append(html: str) -> DatastarEvent:
    return SSE.patch_elements(
        html,
        selector=TRANSCRIPT_SELECTOR,
        mode=ElementPatchMode.APPEND,
    )


def _form(*, conversation_id: str, is_closed: bool, csrf_token: str) -> DatastarEvent:
    return SSE.patch_elements(
        render_message_form(
            conversation_id=conversation_id,
            is_closed=is_closed,
            csrf_token=csrf_token,
        ),
    )


def _reconnect() -> DatastarEvent:
    """A new value of the signal makes the page open a new stream.

    Microseconds: the value stays below the largest safe integer of JavaScript.
    """
    return SSE.patch_signals({STREAM_SIGNAL: time.time_ns() // 1000})


def _patches(*events: DatastarEvent) -> DatastarResponse:
    # An async iterator: under ASGI, Django warns about a sync one.
    async def stream() -> AsyncGenerator[DatastarEvent]:
        for event in events:
            yield event

    return DatastarResponse(stream())


def _error_response(error: DjPydanticAgentsError) -> HttpResponseBase:
    status = next(
        status
        for error_type, status in _ERROR_STATUSES
        if isinstance(error, error_type)
    )
    return HttpResponse(str(error), status=status, content_type="text/plain")
