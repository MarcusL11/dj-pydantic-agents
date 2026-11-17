from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone
from pydantic_ai.messages import ModelRequest
from pydantic_ai.messages import ModelResponse
from pydantic_ai.messages import TextPart
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.messages import UserPromptPart
from pydantic_ai.tools import DeferredToolRequests
from unittest_parametrize import parametrize

from dj_pydantic_agents.dtos.turn_commands import ClaimTurnCommandDTO
from dj_pydantic_agents.dtos.turn_commands import CreateConversationCommandDTO
from dj_pydantic_agents.dtos.turn_commands import DecideApprovalCommandDTO
from dj_pydantic_agents.dtos.turn_commands import DeleteConversationCommandDTO
from dj_pydantic_agents.dtos.turn_commands import FailStaleTurnCommandDTO
from dj_pydantic_agents.dtos.turn_commands import FailTurnCommandDTO
from dj_pydantic_agents.dtos.turn_commands import RenameConversationCommandDTO
from dj_pydantic_agents.dtos.turn_commands import SaveTurnResultCommandDTO
from dj_pydantic_agents.dtos.turn_commands import StartTurnCommandDTO
from dj_pydantic_agents.dtos.turn_commands import TurnUsageDTO
from dj_pydantic_agents.errors import ApprovalNotPending
from dj_pydantic_agents.errors import AttachmentNotPending
from dj_pydantic_agents.errors import ConversationNotFound
from dj_pydantic_agents.errors import TurnInProgress
from dj_pydantic_agents.errors import TurnStateConflict
from dj_pydantic_agents.kit.events import PendingApprovalDTO
from dj_pydantic_agents.kit.history import messages_to_json
from dj_pydantic_agents.kit.history import pending_to_json
from dj_pydantic_agents.models import Attachment
from dj_pydantic_agents.models import Conversation
from dj_pydantic_agents.models import PendingApproval
from dj_pydantic_agents.models import Turn
from dj_pydantic_agents.repositories.turn_command_repository import (
    TurnCommandRepository,
)
from tests.factories import AttachmentFactory
from tests.factories import ConversationFactory
from tests.factories import PendingApprovalFactory
from tests.factories import TurnFactory
from tests.factories import UserFactory
from tests.testcases import TestCase

if TYPE_CHECKING:
    from django.contrib.auth.models import User

SEND_MAIL_CALL = ToolCallPart(
    tool_name="send_mail",
    args={"to": "ada"},
    tool_call_id="call-1",
)
FIRST_RUN_MESSAGES = tuple(
    messages_to_json(
        [
            ModelRequest(parts=[UserPromptPart(content="Mail Ada")]),
            ModelResponse(parts=[SEND_MAIL_CALL]),
        ],
    ),
)
PENDING_JSON = pending_to_json(DeferredToolRequests(approvals=[SEND_MAIL_CALL]))
SEND_MAIL_APPROVAL = PendingApprovalDTO(
    tool_call_id="call-1",
    tool_name="send_mail",
    args_json='{"to":"ada"}',
)
REPLY_MESSAGES = tuple(
    messages_to_json([ModelResponse(parts=[TextPart(content="Done")])]),
)
INPUT_TOKENS = 120
OUTPUT_TOKENS = 30
STALE_SECONDS = 1800


def age_status(turn: Turn, *, seconds: int) -> None:
    """Move the latest status change of the turn back by some seconds."""
    Turn.objects.filter(id=turn.id).update(
        status_changed_at=timezone.now() - timedelta(seconds=seconds),
    )


class TestCreateConversation(TestCase):
    def test_creates_an_empty_conversation_with_a_prefixed_id(self):
        owner = UserFactory.create()

        result = TurnCommandRepository().create_conversation(
            command=CreateConversationCommandDTO(
                owner_id=owner.pk,
                agent_name="assistant",
            ),
        )

        conversation = Conversation.objects.get(id=result.conversation_id)
        assert result.conversation_id.startswith("cnv_")
        assert conversation.owner_id == owner.pk
        assert conversation.agent_name == "assistant"
        assert conversation.title == ""
        assert conversation.messages == []
        assert conversation.pending_approvals is None


class TestRenameConversation(TestCase):
    owner: User
    conversation: Conversation

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create()
        cls.conversation = ConversationFactory.create(owner=cls.owner, title="Old")

    def rename(self, *, title: str = "New title", user_id: int | None = None):
        TurnCommandRepository().rename_conversation(
            command=RenameConversationCommandDTO(
                conversation_id=self.conversation.id,
                user_id=self.owner.pk if user_id is None else user_id,
                title=title,
            ),
        )

    def test_sets_the_title_and_keeps_the_place_in_the_list(self):
        updated_at = self.conversation.updated_at

        self.rename(title="  Blue dial watches  ")

        self.conversation.refresh_from_db()
        assert self.conversation.title == "Blue dial watches"
        assert self.conversation.updated_at == updated_at

    def test_renames_during_an_active_turn(self):
        TurnFactory.create(conversation=self.conversation, requested_by=self.owner)

        self.rename()

        self.conversation.refresh_from_db()
        assert self.conversation.title == "New title"

    def test_another_user_gets_not_found_and_nothing_changes(self):
        other = UserFactory.create()

        with self.assertRaises(ConversationNotFound):
            self.rename(user_id=other.pk)

        self.conversation.refresh_from_db()
        assert self.conversation.title == "Old"


class TestDeleteConversation(TestCase):
    owner: User
    conversation: Conversation

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create()
        cls.conversation = ConversationFactory.create(owner=cls.owner)

    def delete(self, *, user_id: int | None = None):
        return TurnCommandRepository().delete_conversation(
            command=DeleteConversationCommandDTO(
                conversation_id=self.conversation.id,
                user_id=self.owner.pk if user_id is None else user_id,
            ),
        )

    def test_deletes_the_conversation_its_turns_and_its_approvals(self):
        turn = TurnFactory.create(
            conversation=self.conversation,
            requested_by=self.owner,
            status=Turn.Status.DONE,
        )
        PendingApprovalFactory.create(
            turn=turn,
            decision=PendingApproval.Decision.APPROVED,
        )
        kept = ConversationFactory.create(owner=self.owner)

        self.delete()

        assert list(Conversation.objects.values_list("id", flat=True)) == [kept.id]
        assert not Turn.objects.exists()
        assert not PendingApproval.objects.exists()

    def test_returns_the_paths_of_the_deleted_files(self):
        turn = TurnFactory.create(
            conversation=self.conversation,
            status=Turn.Status.DONE,
        )
        sent = AttachmentFactory.create(conversation=self.conversation, turn=turn)
        pending = AttachmentFactory.create(conversation=self.conversation)
        kept = AttachmentFactory.create()

        deleted = self.delete()

        assert set(deleted.attachment_paths) == {str(sent.file), str(pending.file)}
        assert list(Attachment.objects.values_list("id", flat=True)) == [kept.id]

    @parametrize(
        "status",
        [
            (Turn.Status.QUEUED,),
            (Turn.Status.RUNNING,),
            (Turn.Status.WAITING_APPROVAL,),
        ],
    )
    def test_an_active_turn_stops_the_delete(self, status: str):
        TurnFactory.create(
            conversation=self.conversation,
            requested_by=self.owner,
            status=status,
        )

        with self.assertRaises(TurnInProgress):
            self.delete()

        assert Conversation.objects.filter(id=self.conversation.id).exists()
        assert Turn.objects.filter(conversation=self.conversation).exists()

    def test_another_user_gets_not_found_and_nothing_changes(self):
        other = UserFactory.create()

        with self.assertRaises(ConversationNotFound):
            self.delete(user_id=other.pk)

        assert Conversation.objects.filter(id=self.conversation.id).exists()


PENDING_SECONDS = 3600


class TestStartTurn(TestCase):
    owner: User
    conversation: Conversation

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create()
        cls.conversation = ConversationFactory.create(owner=cls.owner)

    def start(
        self,
        *,
        prompt: str = "Hi",
        user_id: int | None = None,
        attachment_ids: tuple[str, ...] = (),
    ):
        return TurnCommandRepository().start_turn(
            command=StartTurnCommandDTO(
                conversation_id=self.conversation.id,
                user_id=self.owner.pk if user_id is None else user_id,
                prompt=prompt,
                attachment_ids=attachment_ids,
            ),
            pending_seconds=PENDING_SECONDS,
        )

    def test_the_turn_takes_the_pending_files_of_the_message(self):
        first = AttachmentFactory.create(
            conversation=self.conversation,
            uploaded_by=self.owner,
            name="a.pdf",
        )
        second = AttachmentFactory.create(
            conversation=self.conversation,
            uploaded_by=self.owner,
            name="b.png",
            media_type="image/png",
        )

        result = self.start(attachment_ids=(second.id, first.id))

        assert [file.name for file in result.attachments] == ["a.pdf", "b.png"]
        assert [file.is_image for file in result.attachments] == [False, True]
        assert set(
            Attachment.objects.filter(turn_id=result.turn_id).values_list(
                "id",
                flat=True,
            ),
        ) == {first.id, second.id}

    @parametrize(
        "case",
        [
            ("expired",),
            ("sent",),
            ("other_user",),
            ("other_conversation",),
            ("missing",),
        ],
    )
    def test_a_file_that_is_not_pending_starts_no_turn(self, case):
        attachment = AttachmentFactory.create(
            conversation=self.conversation,
            uploaded_by=self.owner,
        )
        attachment_id = attachment.id
        match case:
            case "expired":
                Attachment.objects.filter(id=attachment.id).update(
                    created_at=timezone.now() - timedelta(seconds=PENDING_SECONDS + 1),
                )
            case "sent":
                Attachment.objects.filter(id=attachment.id).update(
                    turn=TurnFactory.create(
                        conversation=self.conversation,
                        status=Turn.Status.DONE,
                    ),
                )
            case "other_user":
                Attachment.objects.filter(id=attachment.id).update(
                    uploaded_by=UserFactory.create(),
                )
            case "other_conversation":
                Attachment.objects.filter(id=attachment.id).update(
                    conversation=ConversationFactory.create(owner=self.owner),
                )
            case "missing":
                attachment_id = "att_missing"
        turns_before = Turn.objects.filter(conversation=self.conversation).count()

        with self.assertRaises(AttachmentNotPending):
            self.start(attachment_ids=(attachment_id,))

        assert (
            Turn.objects.filter(conversation=self.conversation).count() == turns_before
        )

    def test_queues_a_turn_and_keeps_the_messages(self):
        result = self.start(prompt="Find the watch\nwith a blue dial")

        turn = Turn.objects.get(id=result.turn_id)
        self.conversation.refresh_from_db()
        assert result.turn_id.startswith("trn_")
        assert result.conversation_id == self.conversation.id
        assert turn.status == Turn.Status.QUEUED
        assert turn.requested_by_id == self.owner.pk
        assert turn.prompt == "Find the watch\nwith a blue dial"
        assert turn.started_at is None
        assert self.conversation.title == "Find the watch"
        assert self.conversation.messages == []

    def test_cuts_a_long_title(self):
        self.start(prompt="word " * 40)

        self.conversation.refresh_from_db()
        assert self.conversation.title.endswith("…")
        assert len(self.conversation.title) <= 80  # noqa: PLR2004

    def test_keeps_a_title(self):
        self.conversation.title = "My title"
        self.conversation.save(update_fields=["title"])

        self.start(prompt="Another subject")

        self.conversation.refresh_from_db()
        assert self.conversation.title == "My title"

    def test_another_user_gets_not_found_and_nothing_changes(self):
        other = UserFactory.create()

        with self.assertRaises(ConversationNotFound):
            self.start(user_id=other.pk)

        assert not Turn.objects.exists()

    def test_a_second_message_during_a_turn_is_rejected(self):
        first = self.start(prompt="One")

        with self.assertRaises(TurnInProgress):
            self.start(prompt="Two")

        assert list(Turn.objects.values_list("id", flat=True)) == [first.turn_id]

    def test_a_message_after_a_failed_turn_starts_a_turn(self):
        TurnFactory.create(
            conversation=self.conversation,
            requested_by=self.owner,
            status=Turn.Status.FAILED,
        )

        result = self.start()

        assert Turn.objects.get(id=result.turn_id).status == Turn.Status.QUEUED

    def test_the_constraint_allows_one_active_turn(self):
        TurnFactory.create(conversation=self.conversation, requested_by=self.owner)

        with (
            transaction.atomic(),
            self.assertRaisesRegex(IntegrityError, "turn_one_active_per_conversation"),
        ):
            TurnFactory.create(
                conversation=self.conversation,
                requested_by=self.owner,
                status=Turn.Status.WAITING_APPROVAL,
            )


class TestClaimTurn(TestCase):
    owner: User
    conversation: Conversation
    turn: Turn

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create()
        cls.conversation = ConversationFactory.create(
            owner=cls.owner,
            messages=list(REPLY_MESSAGES),
        )
        cls.turn = TurnFactory.create(
            conversation=cls.conversation,
            requested_by=cls.owner,
            prompt="Mail Ada",
        )

    def claim(self, *, history_turns: int = 2):
        return TurnCommandRepository().claim_turn(
            command=ClaimTurnCommandDTO(
                turn_id=self.turn.id,
                history_turns=history_turns,
            ),
        )

    def test_a_run_gets_the_files_of_the_latest_turns(self):
        old_turn = TurnFactory.create(conversation=self.conversation, status="done")
        recent_turn = TurnFactory.create(conversation=self.conversation, status="done")
        Turn.objects.filter(id=old_turn.id).update(
            created_at=timezone.now() - timedelta(minutes=2),
        )
        Turn.objects.filter(id=recent_turn.id).update(
            created_at=timezone.now() - timedelta(minutes=1),
        )
        Turn.objects.filter(id=self.turn.id).update(created_at=timezone.now())
        AttachmentFactory.create(conversation=self.conversation, turn=old_turn)
        recent = AttachmentFactory.create(
            conversation=self.conversation,
            turn=recent_turn,
        )
        current = AttachmentFactory.create(
            conversation=self.conversation,
            turn=self.turn,
            name="dial.png",
            media_type="image/png",
        )
        AttachmentFactory.create(conversation=self.conversation)

        run_input = self.claim(history_turns=2)

        assert run_input is not None
        assert [
            (file.attachment_id, file.turn_id) for file in run_input.attachments
        ] == [
            (recent.id, recent_turn.id),
            (current.id, self.turn.id),
        ]
        assert run_input.attachments[1].path == str(current.file)
        assert run_input.attachments[1].media_type == "image/png"

    def test_a_first_run_gets_the_prompt_and_the_history(self):
        run_input = self.claim()

        self.turn.refresh_from_db()
        assert self.turn.status == Turn.Status.RUNNING
        assert self.turn.started_at is not None
        assert run_input is not None
        assert run_input.turn_id == self.turn.id
        assert run_input.conversation_id == self.conversation.id
        assert run_input.agent_name == "assistant"
        assert run_input.user_id == self.owner.pk
        assert run_input.history == REPLY_MESSAGES
        assert run_input.prompt == "Mail Ada"
        assert run_input.pending is None
        assert run_input.decisions is None

    def test_a_second_claim_gets_nothing(self):
        self.claim()

        assert self.claim() is None

    def test_a_resume_gets_the_decisions_and_no_prompt(self):
        Conversation.objects.filter(id=self.conversation.id).update(
            pending_approvals=PENDING_JSON,
        )
        PendingApprovalFactory.create(
            turn=self.turn,
            tool_call_id="call-1",
            decision=PendingApproval.Decision.APPROVED,
        )
        PendingApprovalFactory.create(
            turn=self.turn,
            tool_call_id="call-2",
            decision=PendingApproval.Decision.DENIED,
        )
        started_at = self.turn.started_at

        run_input = self.claim()

        assert run_input is not None
        assert run_input.prompt is None
        assert run_input.pending == PENDING_JSON
        assert run_input.decisions == {"call-1": True, "call-2": False}
        self.turn.refresh_from_db()
        assert started_at is None
        assert self.turn.started_at is not None

    def test_a_claim_moves_the_status_time(self):
        age_status(self.turn, seconds=STALE_SECONDS)
        old = Turn.objects.get(id=self.turn.id).status_changed_at

        self.claim()

        self.turn.refresh_from_db()
        assert self.turn.status_changed_at > old

    def test_keeps_the_first_start_time(self):
        self.claim()
        self.turn.refresh_from_db()
        first_start = self.turn.started_at
        Turn.objects.filter(id=self.turn.id).update(status=Turn.Status.QUEUED)

        self.claim()

        self.turn.refresh_from_db()
        assert self.turn.started_at == first_start


class TestSaveTurnResult(TestCase):
    owner: User
    conversation: Conversation
    turn: Turn

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create()
        cls.conversation = ConversationFactory.create(owner=cls.owner)
        cls.turn = TurnFactory.create(
            conversation=cls.conversation,
            requested_by=cls.owner,
            status=Turn.Status.RUNNING,
        )

    def save_result(self, **overrides):
        values = {
            "turn_id": self.turn.id,
            "new_messages": REPLY_MESSAGES,
            "pending": None,
            "approvals": (),
            "usage": TurnUsageDTO(
                requests=1,
                input_tokens=INPUT_TOKENS,
                output_tokens=OUTPUT_TOKENS,
            ),
        }
        return TurnCommandRepository().save_turn_result(
            command=SaveTurnResultCommandDTO(**{**values, **overrides}),
        )

    def test_a_reply_finishes_the_turn(self):
        result = self.save_result()

        self.turn.refresh_from_db()
        self.conversation.refresh_from_db()
        assert result.status == "done"
        assert self.turn.status == Turn.Status.DONE
        assert self.turn.finished_at is not None
        assert self.turn.requests == 1
        assert self.turn.input_tokens == INPUT_TOKENS
        assert self.turn.output_tokens == OUTPUT_TOKENS
        assert self.conversation.messages == list(REPLY_MESSAGES)
        assert self.conversation.pending_approvals is None

    def test_an_approval_stop_waits_for_decisions(self):
        result = self.save_result(
            new_messages=FIRST_RUN_MESSAGES,
            pending=PENDING_JSON,
            approvals=(SEND_MAIL_APPROVAL,),
        )

        self.turn.refresh_from_db()
        self.conversation.refresh_from_db()
        approval = PendingApproval.objects.get(turn=self.turn)
        assert result.status == "waiting_approval"
        assert self.turn.status == Turn.Status.WAITING_APPROVAL
        assert self.turn.finished_at is None
        assert self.conversation.messages == list(FIRST_RUN_MESSAGES)
        assert self.conversation.pending_approvals == PENDING_JSON
        assert approval.id.startswith("apr_")
        assert approval.tool_call_id == "call-1"
        assert approval.tool_name == "send_mail"
        assert approval.args_json == '{"to":"ada"}'
        assert approval.decision == PendingApproval.Decision.PENDING

    def test_adds_the_messages_and_the_usage_of_two_runs(self):
        self.save_result(
            new_messages=FIRST_RUN_MESSAGES,
            pending=PENDING_JSON,
            approvals=(SEND_MAIL_APPROVAL,),
        )
        Turn.objects.filter(id=self.turn.id).update(status=Turn.Status.RUNNING)

        self.save_result()

        self.turn.refresh_from_db()
        self.conversation.refresh_from_db()
        assert self.turn.requests == 2  # noqa: PLR2004
        assert self.turn.input_tokens == 2 * INPUT_TOKENS
        assert self.conversation.messages == [*FIRST_RUN_MESSAGES, *REPLY_MESSAGES]
        assert self.conversation.pending_approvals is None

    def test_a_turn_that_does_not_run_is_rejected_and_nothing_changes(self):
        Turn.objects.filter(id=self.turn.id).update(status=Turn.Status.QUEUED)

        with self.assertRaises(TurnStateConflict):
            self.save_result()

        self.turn.refresh_from_db()
        self.conversation.refresh_from_db()
        assert self.turn.status == Turn.Status.QUEUED
        assert self.turn.requests == 0
        assert self.conversation.messages == []

    def test_a_failed_insert_rolls_back_the_messages(self):
        PendingApprovalFactory.create(turn=self.turn, tool_call_id="call-1")

        with (
            self.assertRaisesRegex(
                IntegrityError,
                "pendingapproval_tool_call_unique_per_turn",
            ),
            transaction.atomic(),
        ):
            self.save_result(
                new_messages=FIRST_RUN_MESSAGES,
                pending=PENDING_JSON,
                approvals=(SEND_MAIL_APPROVAL,),
            )

        self.conversation.refresh_from_db()
        assert self.conversation.messages == []
        assert self.conversation.pending_approvals is None

    def test_approvals_need_the_pending_requests(self):
        with self.assertRaisesRegex(ValueError, "together"):
            self.save_result(approvals=(SEND_MAIL_APPROVAL,))


class TestFailTurn(TestCase):
    owner: User
    conversation: Conversation
    turn: Turn

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create()
        cls.conversation = ConversationFactory.create(
            owner=cls.owner,
            messages=list(FIRST_RUN_MESSAGES),
            pending_approvals=PENDING_JSON,
        )
        cls.turn = TurnFactory.create(
            conversation=cls.conversation,
            requested_by=cls.owner,
            prompt="Mail Ada",
            status=Turn.Status.RUNNING,
        )

    def fail_the_turn(self):
        TurnCommandRepository().fail_turn(
            command=FailTurnCommandDTO(turn_id=self.turn.id, error_code="usage_limit"),
        )

    def test_records_the_code_and_keeps_the_messages_and_the_prompt(self):
        self.fail_the_turn()

        self.turn.refresh_from_db()
        self.conversation.refresh_from_db()
        assert self.turn.status == Turn.Status.FAILED
        assert self.turn.error_code == "usage_limit"
        assert self.turn.finished_at is not None
        assert self.turn.prompt == "Mail Ada"
        assert self.conversation.messages == list(FIRST_RUN_MESSAGES)
        assert self.conversation.pending_approvals is None

    def test_a_finished_turn_is_rejected(self):
        Turn.objects.filter(id=self.turn.id).update(status=Turn.Status.DONE)

        with self.assertRaises(TurnStateConflict):
            self.fail_the_turn()

        self.conversation.refresh_from_db()
        assert self.conversation.pending_approvals == PENDING_JSON


class TestDecideApproval(TestCase):
    owner: User
    conversation: Conversation
    turn: Turn
    first: PendingApproval
    second: PendingApproval

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create()
        cls.conversation = ConversationFactory.create(owner=cls.owner)
        cls.turn = TurnFactory.create(
            conversation=cls.conversation,
            requested_by=cls.owner,
            status=Turn.Status.WAITING_APPROVAL,
        )
        cls.first = PendingApprovalFactory.create(turn=cls.turn, tool_call_id="call-1")
        cls.second = PendingApprovalFactory.create(
            turn=cls.turn,
            tool_call_id="call-2",
        )

    def decide(self, approval, *, approved=True, user_id=None):
        return TurnCommandRepository().decide_approval(
            command=DecideApprovalCommandDTO(
                approval_id=approval.id,
                user_id=self.owner.pk if user_id is None else user_id,
                approved=approved,
            ),
        )

    def test_records_a_decision_and_waits_for_the_others(self):
        result = self.decide(self.first, approved=False)

        self.first.refresh_from_db()
        self.turn.refresh_from_db()
        assert result.approval_id == self.first.id
        assert result.turn_id == self.turn.id
        assert result.requeued is False
        assert self.first.decision == PendingApproval.Decision.DENIED
        assert self.first.decided_by_id == self.owner.pk
        assert self.first.decided_at is not None
        assert self.turn.status == Turn.Status.WAITING_APPROVAL

    def test_the_last_decision_queues_the_turn_again(self):
        self.decide(self.first)

        result = self.decide(self.second)

        self.turn.refresh_from_db()
        assert result.requeued is True
        assert self.turn.status == Turn.Status.QUEUED

    def test_the_requeue_moves_the_status_time(self):
        age_status(self.turn, seconds=STALE_SECONDS)
        old = Turn.objects.get(id=self.turn.id).status_changed_at

        self.decide(self.first)
        self.decide(self.second)

        self.turn.refresh_from_db()
        assert self.turn.status_changed_at > old

    def test_a_second_decision_is_rejected(self):
        self.decide(self.first)

        with self.assertRaises(ApprovalNotPending):
            self.decide(self.first, approved=False)

        self.first.refresh_from_db()
        assert self.first.decision == PendingApproval.Decision.APPROVED

    def test_another_user_is_rejected_and_nothing_changes(self):
        other = UserFactory.create()

        with self.assertRaises(ApprovalNotPending):
            self.decide(self.first, user_id=other.pk)

        self.first.refresh_from_db()
        assert self.first.decision == PendingApproval.Decision.PENDING
        assert self.first.decided_by_id is None

    def test_a_turn_that_does_not_wait_is_rejected(self):
        Turn.objects.filter(id=self.turn.id).update(status=Turn.Status.RUNNING)

        with self.assertRaises(ApprovalNotPending):
            self.decide(self.first)


class TestFailStaleTurn(TestCase):
    conversation: Conversation
    turn: Turn

    @classmethod
    def setUpTestData(cls):
        cls.conversation = ConversationFactory.create(pending_approvals=PENDING_JSON)
        cls.turn = TurnFactory.create(conversation=cls.conversation)

    def fail_stale(self):
        TurnCommandRepository().fail_stale_turn(
            command=FailStaleTurnCommandDTO(
                turn_id=self.turn.id,
                stale_seconds=STALE_SECONDS,
                error_code="worker_lost",
            ),
        )
        self.turn.refresh_from_db()
        self.conversation.refresh_from_db()

    @parametrize("status", [(Turn.Status.QUEUED,), (Turn.Status.RUNNING,)])
    def test_fails_a_stale_turn_and_clears_the_pending_approvals(self, status):
        Turn.objects.filter(id=self.turn.id).update(status=status)
        age_status(self.turn, seconds=STALE_SECONDS + 1)

        self.fail_stale()

        assert self.turn.status == Turn.Status.FAILED
        assert self.turn.error_code == "worker_lost"
        assert self.turn.finished_at is not None
        assert self.conversation.pending_approvals is None

    def test_keeps_a_recent_turn(self):
        age_status(self.turn, seconds=STALE_SECONDS - 60)

        self.fail_stale()

        assert self.turn.status == Turn.Status.QUEUED
        assert self.conversation.pending_approvals == PENDING_JSON

    def test_keeps_a_turn_that_waits_for_a_decision(self):
        Turn.objects.filter(id=self.turn.id).update(
            status=Turn.Status.WAITING_APPROVAL,
        )
        age_status(self.turn, seconds=STALE_SECONDS + 1)

        self.fail_stale()

        assert self.turn.status == Turn.Status.WAITING_APPROVAL
