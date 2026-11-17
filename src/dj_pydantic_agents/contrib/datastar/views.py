"""The send, approve, stream and file views. Most views return Datastar patches.

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
from django.http import HttpResponseNotAllowed
from django.middleware.csrf import get_token
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST
from pydantic import ValidationError

from dj_pydantic_agents.composition import build_attachment_command_service
from dj_pydantic_agents.composition import build_conversation_command_service
from dj_pydantic_agents.composition import build_conversation_query_service
from dj_pydantic_agents.composition import build_event_transport
from dj_pydantic_agents.composition import build_reply_sanitizer
from dj_pydantic_agents.conf import load_settings
from dj_pydantic_agents.contrib.datastar.dtos import ApprovalDecisionPayloadDTO
from dj_pydantic_agents.contrib.datastar.dtos import SendMessagePayloadDTO
from dj_pydantic_agents.contrib.datastar.rendering import attachment_chip_id
from dj_pydantic_agents.contrib.datastar.rendering import render_approval_actions
from dj_pydantic_agents.contrib.datastar.rendering import render_attachment_error
from dj_pydantic_agents.contrib.datastar.rendering import render_attachment_input
from dj_pydantic_agents.contrib.datastar.rendering import render_attachments
from dj_pydantic_agents.contrib.datastar.rendering import render_message_form
from dj_pydantic_agents.contrib.datastar.rendering import render_reply
from dj_pydantic_agents.contrib.datastar.rendering import render_reply_text
from dj_pydantic_agents.contrib.datastar.rendering import render_run_end
from dj_pydantic_agents.contrib.datastar.rendering import render_tool_steps
from dj_pydantic_agents.contrib.datastar.rendering import render_transcript_line
from dj_pydantic_agents.contrib.datastar.rendering import reply_id
from dj_pydantic_agents.contrib.datastar.rendering import reply_steps_id
from dj_pydantic_agents.contrib.datastar.rendering import reply_text_id
from dj_pydantic_agents.contrib.datastar.streaming import TextReveal
from dj_pydantic_agents.contrib.datastar.streaming import close_open_markdown
from dj_pydantic_agents.contrib.datastar.streaming import number_blocks
from dj_pydantic_agents.db import database_sync_to_async
from dj_pydantic_agents.dtos.attachments import GetAttachmentFileQueryDTO
from dj_pydantic_agents.dtos.attachments import RemoveAttachmentCommandDTO
from dj_pydantic_agents.dtos.attachments import UploadAttachmentsCommandDTO
from dj_pydantic_agents.dtos.attachments import UploadedFileDTO
from dj_pydantic_agents.dtos.turn_commands import DecideApprovalCommandDTO
from dj_pydantic_agents.dtos.turn_commands import StartTurnCommandDTO
from dj_pydantic_agents.dtos.turn_streams import OpenTurnStreamCommandDTO
from dj_pydantic_agents.errors import AgentAccessDenied
from dj_pydantic_agents.errors import AgentNotFound
from dj_pydantic_agents.errors import ApprovalNotPending
from dj_pydantic_agents.errors import AttachmentNotFound
from dj_pydantic_agents.errors import AttachmentNotPending
from dj_pydantic_agents.errors import AttachmentRefused
from dj_pydantic_agents.errors import ConversationNotFound
from dj_pydantic_agents.errors import DjPydanticAgentsError
from dj_pydantic_agents.errors import TurnInProgress
from dj_pydantic_agents.errors import TurnNotQueued
from dj_pydantic_agents.kit.events import START_EVENT_ID
from dj_pydantic_agents.kit.events import ApprovalRequestedEventDTO
from dj_pydantic_agents.kit.events import TextDeltaEventDTO
from dj_pydantic_agents.kit.events import ToolCallEventDTO
from dj_pydantic_agents.kit.events import TurnDoneEventDTO
from dj_pydantic_agents.kit.events import TurnFailedEventDTO

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from collections.abc import Iterator

    from django.core.files.uploadedfile import UploadedFile
    from django.http import HttpRequest
    from django.http.response import HttpResponseBase

    from dj_pydantic_agents.dtos.attachments import AttachmentContentDTO
    from dj_pydantic_agents.dtos.attachments import AttachmentProjectionDTO
    from dj_pydantic_agents.dtos.attachments import PendingAttachmentsProjectionDTO
    from dj_pydantic_agents.dtos.conversation_queries import ApprovalProjectionDTO
    from dj_pydantic_agents.dtos.shared_types import UserId
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
# The time between two steps of the text. Each step is one patch. A model
# sends a part of its text about each 150 ms. Steps of this length fill that
# time with a few words, so the text does not stop between the parts.
STEP_SECONDS = 0.045
# A new stream shows the events that come in this time in one patch. These
# are the events from before the stream, for example after a reload.
CATCH_UP_SECONDS = 0.05
# The signal of the page that opens a new stream when its value changes.
STREAM_SIGNAL = "_djpaStream"
TRANSCRIPT_SELECTOR = "#djpa-transcript"
FORM_SELECTOR = "#djpa-message-form"
ATTACHMENTS_SELECTOR = "#djpa-attachments"
ATTACHMENT_ERROR_SELECTOR = "#djpa-attachments-error"
ATTACHMENT_INPUT_SELECTOR = "#djpa-attachment-input"
# The other fields of an upload request, over the size of its files.
FORM_OVERHEAD_BYTES = 1024 * 1024
# A browser shows these types. It downloads the others.
INLINE_MEDIA_TYPES = ("image/", "application/pdf")
KEEP_ALIVE = DatastarEvent(": keep-alive\n\n")

_ERROR_STATUSES: tuple[tuple[type[DjPydanticAgentsError], int], ...] = (
    (ConversationNotFound, 404),
    (AgentNotFound, 404),
    (AgentAccessDenied, 403),
    (AttachmentNotFound, 404),
    (TurnInProgress, 409),
    (ApprovalNotPending, 409),
)
_HANDLED_ERRORS = tuple(error_type for error_type, _ in _ERROR_STATUSES)


@require_POST
async def send_message(request: HttpRequest, conversation_id: str) -> HttpResponseBase:
    """Start a turn. Show the message, a reply that streams, and a closed form.

    The message takes its pending files. If a file expired, no turn starts,
    and the form shows the error.
    """
    user = await request.auser()
    if not user.is_authenticated:
        return HttpResponse(status=403)
    try:
        payload = SendMessagePayloadDTO(
            prompt=request.POST.get("prompt", ""),
            attachment_ids=tuple(request.POST.getlist("attachment")),
        )
    except ValidationError:
        return HttpResponse(status=400)
    command = StartTurnCommandDTO(
        conversation_id=conversation_id,
        user_id=user.pk,
        prompt=payload.prompt,
        attachment_ids=payload.attachment_ids,
    )
    csrf_token = get_token(request)
    try:
        started = await database_sync_to_async(_start_turn)(command)
    except TurnNotQueued as error:
        message = _user_line(text=payload.prompt, files=())
        return _patches(message, *_failed_turn(error, csrf_token))
    except AttachmentNotPending as error:
        return _patches(_attachment_error(str(error)))
    except _HANDLED_ERRORS as error:
        return _error_response(error)
    return _patches(
        _user_line(text=payload.prompt, files=started.attachments),
        _append(render_reply(turn_id=started.turn_id)),
        _form(conversation_id=conversation_id, is_closed=True, csrf_token=csrf_token),
    )


@require_POST
async def upload_attachments(
    request: HttpRequest,
    conversation_id: str,
) -> HttpResponseBase:
    """Store the files for the next message. Show all its pending files.

    Django keeps a large upload in a temporary file. The size check comes
    before the view reads the files into memory. A refused file shows an
    error, and the pending files stay.
    """
    user = await request.auser()
    if not user.is_authenticated:
        return HttpResponse(status=403)
    if (refused := _oversized_upload(request)) is not None:
        return refused
    csrf_token = get_token(request)
    uploads = request.FILES.getlist("files")
    if not uploads:
        return HttpResponse(status=400)
    try:
        pending = await database_sync_to_async(_upload_attachments)(
            conversation_id=conversation_id,
            user_id=user.pk,
            uploads=uploads,
        )
    except AttachmentRefused as error:
        return _attachment_refused(str(error))
    except _HANDLED_ERRORS as error:
        return _error_response(error)
    return _patches(_attachments(pending, csrf_token=csrf_token))


@require_POST
async def remove_attachment(
    request: HttpRequest,
    attachment_id: str,
) -> HttpResponseBase:
    """Delete a pending file. Show the pending files that stay."""
    user = await request.auser()
    if not user.is_authenticated:
        return HttpResponse(status=403)
    command = RemoveAttachmentCommandDTO(attachment_id=attachment_id, user_id=user.pk)
    try:
        pending = await database_sync_to_async(_remove_attachment)(command)
    except AttachmentNotPending:
        # The file expired or was sent. Its chip goes.
        return _patches(SSE.remove_elements(f"#{attachment_chip_id(attachment_id)}"))
    return _patches(_attachments(pending, csrf_token=get_token(request)))


async def attachment_file(request: HttpRequest, attachment_id: str) -> HttpResponseBase:
    """The bytes of a file, for its owner. A browser shows an image or a PDF."""
    if request.method not in {"GET", "HEAD"}:
        return HttpResponseNotAllowed(["GET", "HEAD"])
    user = await request.auser()
    if not user.is_authenticated:
        return HttpResponse(status=403)
    query = GetAttachmentFileQueryDTO(attachment_id=attachment_id, user_id=user.pk)
    try:
        content = await database_sync_to_async(_attachment_content)(query)
    except _HANDLED_ERRORS as error:
        return _error_response(error)
    return _file_response(content)


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


class _Tick:
    """The reader of a stream yields this when the next text step is due."""


_TICK = _Tick()


class _TurnStream:
    """The events of one stream. It holds no model and no database connection.

    A new stream first catches up: it shows the text of the earlier events in
    one patch. After that, it shows each new text in small, even steps. Each
    patch changes only the blocks of the reply that changed. A tool call adds
    a step line above the text.
    """

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
        self._text = TextReveal()
        # The blocks on the page. None: the next patch replaces the full text.
        self._blocks: tuple[str, ...] | None = None
        # The tool calls of the run, in their order. Each one shows a step line.
        self._steps: list[ToolCallEventDTO] = []
        self._catching_up = True
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
            items = self._with_ticks(reader)
            try:
                async for item in items:
                    if isinstance(item, _Tick):
                        for event in self._tick():
                            yield event
                    elif item is None:
                        yield KEEP_ALIVE
                    elif self._is_earlier_stop(item.event):
                        self._text.clear()
                        self._blocks = None
                        self._steps.clear()
                        after_id = item.event_id
                    else:
                        async for event in self._patches_for(item.event):
                            yield event
            finally:
                await items.aclose()
                await reader.aclose()

    async def _with_ticks(
        self,
        reader: AsyncGenerator[StreamedTurnEventDTO | None],
    ) -> AsyncGenerator[StreamedTurnEventDTO | _Tick | None]:
        """Yield the items of the reader, and a tick when a text step is due.

        A wait for an item does not cancel the read, so a tick cannot lose an
        event. Raise TimeoutError at the deadline.
        """
        loop = asyncio.get_running_loop()
        read: asyncio.Future[StreamedTurnEventDTO | None] | None = None
        try:
            while True:
                if read is None:
                    read = asyncio.ensure_future(anext(reader))
                timeout = self._deadline - loop.time()
                if self._catching_up:
                    timeout = min(timeout, CATCH_UP_SECONDS)
                elif self._text.is_waiting:
                    timeout = min(timeout, STEP_SECONDS)
                done, _ = await asyncio.wait({read}, timeout=max(timeout, 0))
                if not done:
                    if loop.time() >= self._deadline:
                        raise TimeoutError
                    yield _TICK
                    continue
                finished, read = read, None
                try:
                    item = finished.result()
                except StopAsyncIteration:
                    return
                yield item
        finally:
            if read is not None:
                read.cancel()
                await asyncio.wait({read})

    def _tick(self) -> Iterator[DatastarEvent]:
        if self._catching_up:
            self._catching_up = False
            if self._text.shown:
                yield from self._text_patches()
        elif self._text.is_waiting:
            self._text.step()
            yield from self._text_patches()

    def _is_earlier_stop(self, event: TurnEventDTO) -> bool:
        """An approval stop with only decided tool calls is of an earlier run."""
        decided = self._snapshot.decided_tool_call_ids
        return isinstance(event, ApprovalRequestedEventDTO) and all(
            approval.tool_call_id in decided for approval in event.approvals
        )

    async def _patches_for(self, event: TurnEventDTO) -> AsyncGenerator[DatastarEvent]:
        if isinstance(event, TurnDoneEventDTO):
            async for patch in self._show_waiting_text():
                yield patch
        for patch in self._event_patches(event):
            yield patch

    def _event_patches(self, event: TurnEventDTO) -> Iterator[DatastarEvent]:
        match event:
            case TextDeltaEventDTO(text=text):
                return self._add_text(text)
            case ToolCallEventDTO():
                return self._add_step(event)
            case TurnDoneEventDTO(text=text):
                return self._run_end(reply_text=text)
            case TurnFailedEventDTO(error_code=error_code):
                return self._run_end(error_code=error_code)
            case ApprovalRequestedEventDTO():
                # The event has no approval IDs for the buttons. The next
                # stream reads them with its snapshot.
                return iter((_reconnect(),))
            case _:
                return iter(())

    def _add_text(self, text: str) -> Iterator[DatastarEvent]:
        """Show the first step of a new text at once. A catch-up shows all of it."""
        self._text.add(text)
        if self._catching_up:
            self._text.show_all()
            return
        self._text.step()
        yield from self._text_patches()

    def _add_step(self, call: ToolCallEventDTO) -> Iterator[DatastarEvent]:
        """Show a step line for a tool call, and replace all the steps.

        A replacement is safe for a new stream: it replays the steps from the
        first event.
        """
        self._steps.append(call)
        yield SSE.patch_elements(
            render_tool_steps(tool_names=[step.tool_name for step in self._steps]),
            selector=f"#{reply_steps_id(self._snapshot.turn_id)}",
            mode=ElementPatchMode.INNER,
        )

    async def _show_waiting_text(self) -> AsyncGenerator[DatastarEvent]:
        """Show the waiting text in steps, before the end of the run."""
        while self._text.is_waiting and not self._catching_up:
            await asyncio.sleep(STEP_SECONDS)
            for patch in self._tick():
                yield patch

    def _text_patches(self) -> Iterator[DatastarEvent]:
        """Patch the blocks of the shown text that changed since the last patch."""
        text_id = reply_text_id(self._snapshot.turn_id)
        html = render_reply_text(
            text=close_open_markdown(self._text.shown),
            sanitizer=self._sanitizer,
        )
        blocks = number_blocks(html, id_prefix=f"{text_id}-")
        sent, self._blocks = self._blocks, blocks
        if blocks is None or sent is None:
            yield SSE.patch_elements(
                html if blocks is None else "".join(blocks),
                selector=f"#{text_id}",
                mode=ElementPatchMode.INNER,
            )
            return
        for block, sent_block in zip(blocks, sent, strict=False):
            if block != sent_block:
                yield SSE.patch_elements(block)
        if len(blocks) > len(sent):
            yield SSE.patch_elements(
                "".join(blocks[len(sent) :]),
                selector=f"#{text_id}",
                mode=ElementPatchMode.APPEND,
            )
        for index in range(len(blocks), len(sent)):
            yield SSE.remove_elements(f"#{text_id}-{index}")

    def _run_end(
        self,
        *,
        reply_text: str = "",
        approvals: tuple[ApprovalProjectionDTO, ...] = (),
        error_code: str = "",
    ) -> Iterator[DatastarEvent]:
        """Set the form, then put the end of the run in the place of the reply.

        Each tool call of the run stays as a closed tool line, the same as
        after a reload.

        The form goes first. The removal of the reply stops this stream, so
        the page does not get an event after it.
        """
        yield _form(
            conversation_id=self._snapshot.conversation_id,
            is_closed=bool(approvals),
            csrf_token=self._csrf_token,
            focus=not approvals,
        )
        yield SSE.patch_elements(
            render_run_end(
                tool_calls=self._steps,
                reply_text=reply_text,
                approvals=approvals,
                error_code=error_code,
                csrf_token=self._csrf_token,
            ),
            selector=f"#{reply_id(self._snapshot.turn_id)}",
            mode=ElementPatchMode.REPLACE,
        )


def _start_turn(command: StartTurnCommandDTO) -> TurnStartedResultDTO:
    return build_conversation_command_service().start_turn(command=command)


def _upload_attachments(
    *,
    conversation_id: str,
    user_id: UserId,
    uploads: list[UploadedFile],
) -> PendingAttachmentsProjectionDTO:
    """Read the files in the sync thread, not in the event loop."""
    command = UploadAttachmentsCommandDTO(
        conversation_id=conversation_id,
        user_id=user_id,
        files=tuple(
            UploadedFileDTO(name=upload.name or "", data=upload.read())
            for upload in uploads
        ),
    )
    return build_attachment_command_service().upload_attachments(command=command)


def _remove_attachment(
    command: RemoveAttachmentCommandDTO,
) -> PendingAttachmentsProjectionDTO:
    return build_attachment_command_service().remove_attachment(command=command)


def _attachment_content(query: GetAttachmentFileQueryDTO) -> AttachmentContentDTO:
    return build_conversation_query_service().get_attachment_content(query=query)


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


def _user_line(
    *,
    text: str,
    files: tuple[AttachmentProjectionDTO, ...],
) -> DatastarEvent:
    return _append(render_transcript_line(kind="user", text=text, files=files))


def _attachments(
    pending: PendingAttachmentsProjectionDTO,
    *,
    csrf_token: str,
) -> DatastarEvent:
    """Replace the area, so that the file input is new and empty."""
    return SSE.patch_elements(
        render_attachments(
            attachments=pending.attachments,
            is_closed=False,
            csrf_token=csrf_token,
        ),
        selector=ATTACHMENTS_SELECTOR,
        mode=ElementPatchMode.REPLACE,
    )


def _attachment_error(message: str) -> DatastarEvent:
    return SSE.patch_elements(
        render_attachment_error(message=message),
        selector=ATTACHMENT_ERROR_SELECTOR,
        mode=ElementPatchMode.REPLACE,
    )


def _oversized_upload(request: HttpRequest) -> HttpResponseBase | None:
    """A response for a request over the limit, before the view reads the files."""
    limit = load_settings().attachment_max_message_bytes + FORM_OVERHEAD_BYTES
    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        return HttpResponse(status=400)
    if length <= limit:
        return None
    megabytes = limit // (1024 * 1024)
    return _attachment_refused(f"The upload is larger than {megabytes} MB.")


def _attachment_refused(message: str) -> DatastarResponse:
    """Show the error and a new, empty file input. The pending files stay."""
    return _patches(
        _attachment_error(message),
        SSE.patch_elements(
            render_attachment_input(is_closed=False),
            selector=ATTACHMENT_INPUT_SELECTOR,
            mode=ElementPatchMode.REPLACE,
        ),
    )


def _file_response(content: AttachmentContentDTO) -> HttpResponse:
    response = HttpResponse(content.data, content_type=content.media_type)
    inline = content.media_type.startswith(INLINE_MEDIA_TYPES)
    disposition = content_disposition_header(
        as_attachment=not inline,
        filename=content.name,
    )
    if disposition is not None:
        response.headers["Content-Disposition"] = disposition
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _append(html: str) -> DatastarEvent:
    return SSE.patch_elements(
        html,
        selector=TRANSCRIPT_SELECTOR,
        mode=ElementPatchMode.APPEND,
    )


def _form(
    *,
    conversation_id: str,
    is_closed: bool,
    csrf_token: str,
    focus: bool = False,
) -> DatastarEvent:
    """Replace the form, not morph it: a morph keeps the typed text."""
    return SSE.patch_elements(
        render_message_form(
            conversation_id=conversation_id,
            is_closed=is_closed,
            csrf_token=csrf_token,
            focus=focus,
        ),
        selector=FORM_SELECTOR,
        mode=ElementPatchMode.REPLACE,
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
