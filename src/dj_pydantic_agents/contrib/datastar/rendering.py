"""Render the package templates to HTML. The views choose the patch targets."""

from typing import TYPE_CHECKING
from typing import Literal

from django.template import loader

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dj_pydantic_agents.dtos.conversation_queries import ApprovalProjectionDTO
    from dj_pydantic_agents.extensions import ReplySanitizer

TEMPLATES = "dj_pydantic_agents"

type Decision = Literal["approved", "denied"]


def reply_id(turn_id: str) -> str:
    return f"djpa-reply-{turn_id}"


def reply_text_id(turn_id: str) -> str:
    return f"{reply_id(turn_id)}-text"


def reply_steps_id(turn_id: str) -> str:
    return f"{reply_id(turn_id)}-steps"


def render_transcript_line(*, kind: str, text: str) -> str:
    return _render(
        f"{TEMPLATES}/transcript_line.html",
        {"kind": kind, "text": text},
    )


def render_reply(*, turn_id: str) -> str:
    return _render(f"{TEMPLATES}/reply.html", {"turn_id": turn_id})


def render_tool_steps(*, tool_names: Sequence[str]) -> str:
    return _render(f"{TEMPLATES}/tool_steps.html", {"tool_names": tool_names})


def render_reply_text(*, text: str, sanitizer: ReplySanitizer) -> str:
    return sanitizer.to_html(text=text)


def render_run_end(
    *,
    reply_text: str = "",
    approvals: Sequence[ApprovalProjectionDTO] = (),
    error_code: str = "",
    csrf_token: str,
) -> str:
    return _render(
        f"{TEMPLATES}/run_end.html",
        {
            "reply_text": reply_text,
            "approvals": approvals,
            "error_code": error_code,
            "csrf_token": csrf_token,
        },
    )


def render_message_form(
    *,
    conversation_id: str,
    is_closed: bool,
    csrf_token: str,
    focus: bool = False,
) -> str:
    return _render(
        f"{TEMPLATES}/message_form.html",
        {
            "conversation_id": conversation_id,
            "is_closed": is_closed,
            "csrf_token": csrf_token,
            "focus": focus,
        },
    )


def render_approval_actions(*, approval_id: str, decision: Decision) -> str:
    return _render(
        f"{TEMPLATES}/approval_card.html#actions",
        {"approval": {"approval_id": approval_id}, "decision": decision},
    )


def _render(template_name: str, context: dict[str, object]) -> str:
    # Remove the empty lines of the load tags and the comments.
    return loader.render_to_string(template_name, context).strip()
