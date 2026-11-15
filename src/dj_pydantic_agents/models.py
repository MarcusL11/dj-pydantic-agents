"""Conversations, their turns and the tool calls that wait for approval."""

from django.conf import settings
from django.db import models

from dj_pydantic_agents.ids import ID_LENGTH
from dj_pydantic_agents.ids import new_approval_id
from dj_pydantic_agents.ids import new_conversation_id
from dj_pydantic_agents.ids import new_turn_id


class Conversation(models.Model):
    id = models.CharField(
        verbose_name="identifier",
        help_text="Prefixed ULID of this conversation, for example cnv_01m7f5c8m8x.",
        primary_key=True,
        max_length=ID_LENGTH,
        default=new_conversation_id,
        editable=False,
    )
    agent_name = models.CharField(
        verbose_name="agent name",
        help_text="Name of the agent spec that answers in this conversation.",
        max_length=100,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="owner",
        help_text="The only user who can read and send messages here.",
        on_delete=models.CASCADE,
        related_name="agent_conversations",
    )
    title = models.CharField(
        verbose_name="title",
        help_text="Short title. Empty until the first message sets it.",
        max_length=200,
        blank=True,
    )
    messages = models.JSONField(
        verbose_name="messages",
        help_text="The Pydantic AI message history, as JSON.",
        default=list,
        blank=True,
    )
    pending_approvals = models.JSONField(
        verbose_name="pending approvals",
        help_text=(
            "The deferred tool requests of the active turn, as JSON. "
            "Null when no tool call waits for a decision."
        ),
        null=True,
        blank=True,
    )
    metadata = models.JSONField(
        verbose_name="metadata",
        help_text="Free data that the project adds. The package does not read it.",
        default=dict,
        blank=True,
    )
    created_at = models.DateTimeField(
        verbose_name="created at",
        help_text="Time this conversation started.",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        verbose_name="updated at",
        help_text="Time of the latest change.",
        auto_now=True,
    )

    class Meta:
        verbose_name = "conversation"
        verbose_name_plural = "conversations"

    def __str__(self) -> str:
        return self.title or str(self.id)


class TurnStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    WAITING_APPROVAL = "waiting_approval", "Waiting for approval"
    DONE = "done", "Done"
    FAILED = "failed", "Failed"


# A conversation has one turn in these states at most.
ACTIVE_TURN_STATUSES = (
    TurnStatus.QUEUED,
    TurnStatus.RUNNING,
    TurnStatus.WAITING_APPROVAL,
)


class Turn(models.Model):
    Status = TurnStatus

    id = models.CharField(
        verbose_name="identifier",
        help_text="Prefixed ULID of this turn. The event stream key.",
        primary_key=True,
        max_length=ID_LENGTH,
        default=new_turn_id,
        editable=False,
    )
    conversation = models.ForeignKey(
        Conversation,
        verbose_name="conversation",
        help_text="The conversation of this turn.",
        on_delete=models.CASCADE,
        related_name="turns",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="requested by",
        help_text="The user who sent the message of this turn.",
        on_delete=models.CASCADE,
        related_name="agent_turns",
    )
    prompt = models.TextField(
        verbose_name="prompt",
        help_text="The user message of this turn.",
    )
    status = models.CharField(
        verbose_name="status",
        help_text="The state of this turn.",
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    requests = models.PositiveIntegerField(
        verbose_name="requests",
        help_text="Model requests of this turn.",
        default=0,
    )
    tool_calls = models.PositiveIntegerField(
        verbose_name="tool calls",
        help_text="Successful tool calls of this turn.",
        default=0,
    )
    input_tokens = models.PositiveIntegerField(
        verbose_name="input tokens",
        help_text="Input tokens of this turn. Includes the cache tokens.",
        default=0,
    )
    output_tokens = models.PositiveIntegerField(
        verbose_name="output tokens",
        help_text="Output tokens of this turn. Includes the reasoning tokens.",
        default=0,
    )
    cache_read_tokens = models.PositiveIntegerField(
        verbose_name="cache read tokens",
        help_text="Input tokens read from the cache of the provider.",
        default=0,
    )
    cache_write_tokens = models.PositiveIntegerField(
        verbose_name="cache write tokens",
        help_text="Input tokens written to the cache of the provider.",
        default=0,
    )
    output_reasoning_tokens = models.PositiveIntegerField(
        verbose_name="output reasoning tokens",
        help_text="Reasoning tokens of this turn.",
        default=0,
    )
    error_code = models.CharField(
        verbose_name="error code",
        help_text="Why the turn failed. Empty if it did not fail.",
        max_length=50,
        blank=True,
    )
    created_at = models.DateTimeField(
        verbose_name="created at",
        help_text="Time the message went into the queue.",
        auto_now_add=True,
    )
    started_at = models.DateTimeField(
        verbose_name="started at",
        help_text="Time the first run started. Null while the turn is in the queue.",
        null=True,
        blank=True,
    )
    finished_at = models.DateTimeField(
        verbose_name="finished at",
        help_text="Time the turn was done or failed. Null until then.",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "turn"
        verbose_name_plural = "turns"
        constraints = [
            models.UniqueConstraint(
                fields=["conversation"],
                condition=models.Q(status__in=ACTIVE_TURN_STATUSES),
                name="turn_one_active_per_conversation",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.id} ({self.get_status_display()})"


class PendingApproval(models.Model):
    class Decision(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"

    id = models.CharField(
        verbose_name="identifier",
        help_text="Prefixed ULID of this approval. The approve button sends it.",
        primary_key=True,
        max_length=ID_LENGTH,
        default=new_approval_id,
        editable=False,
    )
    turn = models.ForeignKey(
        Turn,
        verbose_name="turn",
        help_text="The turn that stopped for this tool call.",
        on_delete=models.CASCADE,
        related_name="approvals",
    )
    tool_call_id = models.CharField(
        verbose_name="tool call identifier",
        help_text="The identifier that the model gave to the tool call.",
        max_length=200,
    )
    tool_name = models.CharField(
        verbose_name="tool name",
        help_text="The name of the tool that the model wants to call.",
        max_length=200,
    )
    args_json = models.TextField(
        verbose_name="arguments",
        help_text="The tool arguments, as the JSON text from the model.",
    )
    decision = models.CharField(
        verbose_name="decision",
        help_text="The decision of the user.",
        max_length=20,
        choices=Decision.choices,
        default=Decision.PENDING,
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="decided by",
        help_text="The user who made the decision. Null while it is pending.",
        on_delete=models.SET_NULL,
        related_name="agent_approval_decisions",
        null=True,
        blank=True,
    )
    decided_at = models.DateTimeField(
        verbose_name="decided at",
        help_text="Time of the decision. Null while it is pending.",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "pending approval"
        verbose_name_plural = "pending approvals"
        constraints = [
            models.UniqueConstraint(
                fields=["turn", "tool_call_id"],
                name="pendingapproval_tool_call_unique_per_turn",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tool_name} ({self.get_decision_display()})"
