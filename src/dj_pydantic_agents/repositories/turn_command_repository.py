"""Complete atomic mutations of conversations, turns and approvals."""

from typing import Literal

from django.db import transaction
from django.db.models import F
from django.db.models.functions import Coalesce
from django.db.models.functions import Now
from django.utils import timezone

from dj_pydantic_agents.dtos.turn_commands import ApprovalDecidedResultDTO
from dj_pydantic_agents.dtos.turn_commands import ClaimTurnCommandDTO
from dj_pydantic_agents.dtos.turn_commands import ConversationCreatedResultDTO
from dj_pydantic_agents.dtos.turn_commands import CreateConversationCommandDTO
from dj_pydantic_agents.dtos.turn_commands import DecideApprovalCommandDTO
from dj_pydantic_agents.dtos.turn_commands import FailTurnCommandDTO
from dj_pydantic_agents.dtos.turn_commands import SaveTurnResultCommandDTO
from dj_pydantic_agents.dtos.turn_commands import StartTurnCommandDTO
from dj_pydantic_agents.dtos.turn_commands import TurnRunInputDTO
from dj_pydantic_agents.dtos.turn_commands import TurnSavedResultDTO
from dj_pydantic_agents.dtos.turn_commands import TurnStartedResultDTO
from dj_pydantic_agents.errors import ApprovalNotPending
from dj_pydantic_agents.errors import ConversationNotFound
from dj_pydantic_agents.errors import TurnInProgress
from dj_pydantic_agents.errors import TurnStateConflict
from dj_pydantic_agents.models import ACTIVE_TURN_STATUSES
from dj_pydantic_agents.models import Conversation
from dj_pydantic_agents.models import PendingApproval
from dj_pydantic_agents.models import Turn

TITLE_LENGTH = 80


class TurnCommandRepository:
    """Start, claim, save, fail and decide turns.

    A lock on the conversation row makes the turns of one conversation run one
    at a time. The partial unique constraint on Turn is the last guard.
    """

    @transaction.atomic
    def create_conversation(
        self,
        *,
        command: CreateConversationCommandDTO,
    ) -> ConversationCreatedResultDTO:
        conversation = Conversation(  # type: ignore[misc]
            agent_name=command.agent_name,
            owner_id=command.owner_id,
            title=command.title,
        )
        conversation.save(force_insert=True)
        return ConversationCreatedResultDTO(conversation_id=conversation.id)

    @transaction.atomic
    def start_turn(self, *, command: StartTurnCommandDTO) -> TurnStartedResultDTO:
        conversation = (
            Conversation.objects.select_for_update()  # type: ignore[misc]
            .filter(id=command.conversation_id, owner_id=command.user_id)
            .first()
        )
        if conversation is None:
            msg = "The conversation was not found."
            raise ConversationNotFound(msg)
        if Turn.objects.filter(
            conversation_id=conversation.id,
            status__in=ACTIVE_TURN_STATUSES,
        ).exists():
            msg = "The conversation has an active turn."
            raise TurnInProgress(msg)

        if not conversation.title:
            conversation.title = _title_from_prompt(command.prompt)
            conversation.save(update_fields=["title", "updated_at"])
        turn = Turn(  # type: ignore[misc]
            conversation_id=conversation.id,
            requested_by_id=command.user_id,
            prompt=command.prompt,
        )
        turn.save(force_insert=True)
        return TurnStartedResultDTO(turn_id=turn.id, conversation_id=conversation.id)

    @transaction.atomic
    def claim_turn(self, *, command: ClaimTurnCommandDTO) -> TurnRunInputDTO | None:
        """Move a queued turn to running. Return None if the turn is not queued.

        A task that comes two times claims nothing the second time.
        """
        claimed = Turn.objects.filter(
            id=command.turn_id,
            status=Turn.Status.QUEUED,
        ).update(
            status=Turn.Status.RUNNING,
            started_at=Coalesce(F("started_at"), Now()),
        )
        if not claimed:
            return None

        turn = Turn.objects.select_related("conversation").get(id=command.turn_id)
        conversation = turn.conversation
        pending = conversation.pending_approvals
        decisions = None
        if pending is not None:
            decisions = {
                tool_call_id: decision == PendingApproval.Decision.APPROVED
                for tool_call_id, decision in turn.approvals.exclude(
                    decision=PendingApproval.Decision.PENDING,
                ).values_list("tool_call_id", "decision")
            }
        return TurnRunInputDTO(
            turn_id=turn.id,
            conversation_id=conversation.id,
            agent_name=conversation.agent_name,
            user_id=turn.requested_by_id,
            history=tuple(conversation.messages),
            prompt=turn.prompt if pending is None else None,
            pending=pending,
            decisions=decisions,
        )

    @transaction.atomic
    def save_turn_result(
        self,
        *,
        command: SaveTurnResultCommandDTO,
    ) -> TurnSavedResultDTO:
        turn = _locked_turn(
            turn_id=command.turn_id,
            statuses=(Turn.Status.RUNNING,),
        )
        conversation = turn.conversation
        conversation.messages = [*conversation.messages, *command.new_messages]
        conversation.pending_approvals = command.pending
        conversation.save(
            update_fields=["messages", "pending_approvals", "updated_at"],
        )

        PendingApproval.objects.bulk_create(
            PendingApproval(
                turn_id=turn.id,
                tool_call_id=approval.tool_call_id,
                tool_name=approval.tool_name,
                args_json=approval.args_json,
            )
            for approval in command.approvals
        )
        usage = command.usage
        status: Literal["waiting_approval", "done"] = (
            "waiting_approval" if command.approvals else "done"
        )
        Turn.objects.filter(id=turn.id).update(
            status=status,
            finished_at=Now() if status == Turn.Status.DONE else None,
            requests=F("requests") + usage.requests,
            tool_calls=F("tool_calls") + usage.tool_calls,
            input_tokens=F("input_tokens") + usage.input_tokens,
            output_tokens=F("output_tokens") + usage.output_tokens,
            cache_read_tokens=F("cache_read_tokens") + usage.cache_read_tokens,
            cache_write_tokens=F("cache_write_tokens") + usage.cache_write_tokens,
            output_reasoning_tokens=F("output_reasoning_tokens")
            + usage.output_reasoning_tokens,
        )
        return TurnSavedResultDTO(turn_id=turn.id, status=status)

    @transaction.atomic
    def fail_turn(self, *, command: FailTurnCommandDTO) -> None:
        """Mark an active turn as failed. Keep the messages and the prompt.

        The pending approvals go, so the conversation can take a new message.
        """
        turn = _locked_turn(turn_id=command.turn_id, statuses=ACTIVE_TURN_STATUSES)
        conversation = turn.conversation
        conversation.pending_approvals = None
        conversation.save(update_fields=["pending_approvals", "updated_at"])
        turn.status = Turn.Status.FAILED
        turn.error_code = command.error_code
        turn.finished_at = timezone.now()
        turn.save(update_fields=["status", "error_code", "finished_at"])

    @transaction.atomic
    def decide_approval(
        self,
        *,
        command: DecideApprovalCommandDTO,
    ) -> ApprovalDecidedResultDTO:
        """Record one decision. Queue the turn again after its last decision."""
        approval = (
            PendingApproval.objects.select_for_update(of=("self", "turn"))  # type: ignore[misc]
            .select_related("turn")
            .filter(
                id=command.approval_id,
                decision=PendingApproval.Decision.PENDING,
                turn__status=Turn.Status.WAITING_APPROVAL,
                turn__conversation__owner_id=command.user_id,
            )
            .first()
        )
        if approval is None:
            msg = "The approval does not wait for a decision."
            raise ApprovalNotPending(msg)

        approval.decision = (
            PendingApproval.Decision.APPROVED
            if command.approved
            else PendingApproval.Decision.DENIED
        )
        approval.decided_by_id = command.user_id  # type: ignore[assignment]
        approval.decided_at = timezone.now()
        approval.save(update_fields=["decision", "decided_by", "decided_at"])

        requeued = not PendingApproval.objects.filter(
            turn_id=approval.turn_id,
            decision=PendingApproval.Decision.PENDING,
        ).exists()
        if requeued:
            Turn.objects.filter(id=approval.turn_id).update(
                status=Turn.Status.QUEUED,
            )
        return ApprovalDecidedResultDTO(
            approval_id=approval.id,
            turn_id=approval.turn_id,
            requeued=requeued,
        )


def _locked_turn(*, turn_id: str, statuses: tuple[str, ...]) -> Turn:
    """Lock the turn and its conversation, or raise if the status does not match."""
    turn = (
        Turn.objects.select_for_update()
        .select_related("conversation")
        .filter(id=turn_id, status__in=statuses)
        .first()
    )
    if turn is None:
        msg = f"The turn is not in one of these states: {', '.join(statuses)}."
        raise TurnStateConflict(msg)
    return turn


def _title_from_prompt(prompt: str) -> str:
    """The first line of the prompt, cut to TITLE_LENGTH characters."""
    first_line = next(
        (line.strip() for line in prompt.splitlines() if line.strip()),
        "",
    )
    if len(first_line) <= TITLE_LENGTH:
        return first_line
    return f"{first_line[: TITLE_LENGTH - 1].rstrip()}…"
