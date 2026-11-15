"""Read the conversation page."""

from typing import cast

from dj_pydantic_agents.dtos.conversation_queries import ActiveTurnProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import ActiveTurnStatus
from dj_pydantic_agents.dtos.conversation_queries import AgentNameProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import ApprovalProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import ConversationPageProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import GetApprovalAgentQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import GetConversationAgentQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import GetConversationPageQueryDTO
from dj_pydantic_agents.errors import ApprovalNotPending
from dj_pydantic_agents.errors import ConversationNotFound
from dj_pydantic_agents.kit.history import messages_from_json
from dj_pydantic_agents.kit.transcript import transcript_lines
from dj_pydantic_agents.models import ACTIVE_TURN_STATUSES
from dj_pydantic_agents.models import Conversation
from dj_pydantic_agents.models import PendingApproval
from dj_pydantic_agents.models import Turn


class ConversationQueryRepository:
    def get_conversation_agent(
        self,
        *,
        query: GetConversationAgentQueryDTO,
    ) -> AgentNameProjectionDTO:
        agent_name = (
            Conversation.objects.filter(
                id=query.conversation_id,
                owner_id=query.user_id,  # type: ignore[misc]
            )
            .values_list("agent_name", flat=True)
            .first()
        )
        if agent_name is None:
            msg = "The conversation was not found."
            raise ConversationNotFound(msg)
        return AgentNameProjectionDTO(agent_name=agent_name)

    def get_approval_agent(
        self,
        *,
        query: GetApprovalAgentQueryDTO,
    ) -> AgentNameProjectionDTO:
        agent_name = (
            PendingApproval.objects.filter(
                id=query.approval_id,
                turn__conversation__owner_id=query.user_id,  # type: ignore[misc]
            )
            .values_list("turn__conversation__agent_name", flat=True)
            .first()
        )
        if agent_name is None:
            msg = "The approval does not wait for a decision."
            raise ApprovalNotPending(msg)
        return AgentNameProjectionDTO(agent_name=agent_name)

    def get_conversation_page(
        self,
        *,
        query: GetConversationPageQueryDTO,
    ) -> ConversationPageProjectionDTO:
        conversation = (
            Conversation.objects.filter(  # type: ignore[misc]
                id=query.conversation_id,
                owner_id=query.user_id,
            )
            .values("id", "agent_name", "title", "messages", "pending_approvals")
            .first()
        )
        if conversation is None:
            msg = "The conversation was not found."
            raise ConversationNotFound(msg)

        turn = (
            Turn.objects.filter(
                conversation_id=conversation["id"],
                status__in=ACTIVE_TURN_STATUSES,
            )
            .values("id", "status", "prompt")
            .first()
        )
        active_turn = None
        approvals: tuple[ApprovalProjectionDTO, ...] = ()
        if turn is not None:
            # A first run saves its messages at the end. Until then, only the
            # turn holds the prompt.
            first_run = conversation["pending_approvals"] is None
            active_turn = ActiveTurnProjectionDTO(
                turn_id=turn["id"],
                status=cast("ActiveTurnStatus", turn["status"]),
                unsaved_prompt=turn["prompt"] if first_run else None,
            )
            approvals = _pending_approvals(turn_id=turn["id"])

        return ConversationPageProjectionDTO(
            conversation_id=conversation["id"],
            agent_name=conversation["agent_name"],
            title=conversation["title"],
            lines=transcript_lines(messages_from_json(conversation["messages"])),
            active_turn=active_turn,
            approvals=approvals,
        )


def _pending_approvals(*, turn_id: str) -> tuple[ApprovalProjectionDTO, ...]:
    return tuple(
        ApprovalProjectionDTO(
            approval_id=approval["id"],
            tool_name=approval["tool_name"],
            args_json=approval["args_json"],
        )
        for approval in PendingApproval.objects.filter(
            turn_id=turn_id,
            decision=PendingApproval.Decision.PENDING,
        )
        .order_by("id")
        .values("id", "tool_name", "args_json")
    )
