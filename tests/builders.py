"""DTO builders for the service tests. They import no model and no factory."""

from typing import Any

from dj_pydantic_agents.dtos.attachments import AttachmentProjectionDTO
from dj_pydantic_agents.dtos.attachments import RunAttachmentDTO
from dj_pydantic_agents.dtos.conversation_queries import AgentNameProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import ConversationPageProjectionDTO
from dj_pydantic_agents.dtos.turn_commands import ApprovalDecidedResultDTO
from dj_pydantic_agents.dtos.turn_commands import TurnRunInputDTO
from dj_pydantic_agents.dtos.turn_commands import TurnSavedResultDTO
from dj_pydantic_agents.dtos.turn_commands import TurnStartedResultDTO
from dj_pydantic_agents.dtos.turn_streams import TurnSnapshotProjectionDTO

CONVERSATION_ID = "cnv_01m7f5c8m8xzp0zy3vmbgzbdw9"
TURN_ID = "trn_01m7f5c8m8xzp0zy3vmbgzbdw9"
APPROVAL_ID = "apr_01m7f5c8m8xzp0zy3vmbgzbdw9"
USER_ID = 7
ATTACHMENT_ID = "att_01m7f5c8m8xzp0zy3vmbgzbdw9"


def a_run_input(**overrides: Any) -> TurnRunInputDTO:
    values: dict[str, Any] = {
        "turn_id": TURN_ID,
        "conversation_id": CONVERSATION_ID,
        "agent_name": "assistant",
        "user_id": USER_ID,
        "history": (),
        "prompt": "Hi",
        "pending": None,
        "decisions": None,
    }
    return TurnRunInputDTO(**{**values, **overrides})


def a_saved_result(**overrides: Any) -> TurnSavedResultDTO:
    return TurnSavedResultDTO(**{"turn_id": TURN_ID, "status": "done", **overrides})


def a_started_result() -> TurnStartedResultDTO:
    return TurnStartedResultDTO(turn_id=TURN_ID, conversation_id=CONVERSATION_ID)


def a_decided_result(**overrides: Any) -> ApprovalDecidedResultDTO:
    values = {
        "approval_id": APPROVAL_ID,
        "turn_id": TURN_ID,
        "conversation_id": CONVERSATION_ID,
        "requeued": False,
    }
    return ApprovalDecidedResultDTO(**{**values, **overrides})


def an_agent(agent_name: str = "assistant") -> AgentNameProjectionDTO:
    return AgentNameProjectionDTO(agent_name=agent_name)


def a_page(**overrides: Any) -> ConversationPageProjectionDTO:
    values: dict[str, Any] = {
        "conversation_id": CONVERSATION_ID,
        "agent_name": "assistant",
        "title": "",
        "lines": (),
        "active_turn": None,
        "approvals": (),
    }
    return ConversationPageProjectionDTO(**{**values, **overrides})


def a_snapshot(**overrides: Any) -> TurnSnapshotProjectionDTO:
    values: dict[str, Any] = {
        "turn_id": TURN_ID,
        "conversation_id": CONVERSATION_ID,
        "status": "running",
        "reply_text": "",
        "error_code": "",
        "approvals": (),
        "decided_tool_call_ids": (),
    }
    return TurnSnapshotProjectionDTO(**{**values, **overrides})


def an_attachment(**overrides: Any) -> AttachmentProjectionDTO:
    values: dict[str, Any] = {
        "attachment_id": ATTACHMENT_ID,
        "name": "invoice.pdf",
        "media_type": "application/pdf",
        "size": 8,
        "is_image": False,
    }
    return AttachmentProjectionDTO(**{**values, **overrides})


def a_run_attachment(**overrides: Any) -> RunAttachmentDTO:
    values: dict[str, Any] = {
        "attachment_id": ATTACHMENT_ID,
        "turn_id": TURN_ID,
        "path": f"dj_pydantic_agents/attachments/{CONVERSATION_ID}/{ATTACHMENT_ID}.pdf",
        "name": "invoice.pdf",
        "media_type": "application/pdf",
    }
    return RunAttachmentDTO(**{**values, **overrides})
