from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from pydantic_ai.messages import ModelRequest
from pydantic_ai.messages import ModelResponse
from pydantic_ai.messages import TextPart
from pydantic_ai.messages import UserPromptPart

from dj_pydantic_agents.conf import SETTING_NAME
from dj_pydantic_agents.contrib.datastar import views
from dj_pydantic_agents.kit.events import ApprovalRequestedEventDTO
from dj_pydantic_agents.kit.events import PendingApprovalDTO
from dj_pydantic_agents.kit.events import TextDeltaEventDTO
from dj_pydantic_agents.kit.events import ToolCallEventDTO
from dj_pydantic_agents.kit.events import TurnDoneEventDTO
from dj_pydantic_agents.kit.events import TurnFailedEventDTO
from dj_pydantic_agents.kit.history import messages_to_json
from dj_pydantic_agents.models import PendingApproval
from dj_pydantic_agents.models import Turn
from tests.contrib.datastar.sse import Patch
from tests.contrib.datastar.sse import read_patches
from tests.contrib.datastar.transports import ScriptedTransport
from tests.factories import ConversationFactory
from tests.factories import TurnFactory
from tests.factories import UserFactory
from tests.testcases import TestCase

SCRIPTED_TRANSPORT = "tests.contrib.datastar.transports.ScriptedTransport"
STALE_SECONDS = 1800
SHORT_STREAM_SECONDS = 0.05
SEND_MAIL = PendingApprovalDTO(
    tool_call_id="call-1",
    tool_name="send_mail",
    args_json='{"to":"ada"}',
)
NEW_CALL = SEND_MAIL.model_copy(update={"tool_call_id": "call-2"})


def scripted_settings():
    return override_settings(
        **{
            SETTING_NAME: {
                "SPECS": "tests.fakes.build_specs",
                "MODEL_FACTORY": "tests.fakes.FakeModelFactory",
                "EVENT_TRANSPORT": SCRIPTED_TRANSPORT,
                "TASK_RUNNER": "tests.fakes.FakeTaskRunner",
            },
        },
    )


class TestStreamTurn(TestCase):
    owner: User
    turn: Turn

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create(is_staff=True)
        conversation = ConversationFactory.create(
            owner=cls.owner,
            messages=messages_to_json(
                [
                    ModelRequest(parts=[UserPromptPart(content="Hi")]),
                    ModelResponse(parts=[TextPart(content="Hello **Ada**")]),
                ],
            ),
        )
        cls.turn = TurnFactory.create(
            conversation=conversation,
            requested_by=cls.owner,
            status=Turn.Status.RUNNING,
        )

    def setUp(self):
        ScriptedTransport.reset()
        settings = scripted_settings()
        settings.enable()
        self.addCleanup(settings.disable)

    async def stream(self, *, user=None) -> list[Patch]:
        await self.async_client.aforce_login(user or self.owner)
        response = await self.async_client.get(
            reverse("dj_pydantic_agents:stream_turn", args=[self.turn.id]),
        )
        assert response.status_code == 200  # noqa: PLR2004
        return await read_patches(response)

    async def set_turn(self, **fields):
        await Turn.objects.filter(id=self.turn.id).aupdate(**fields)

    def assert_run_end(self, patch: Patch) -> None:
        assert patch.selector == f"#djpa-reply-{self.turn.id}"
        assert patch.mode == "replace"

    async def test_renders_the_full_text_at_each_text_event(self):
        ScriptedTransport.script = [
            TextDeltaEventDTO(text="Hello"),
            ToolCallEventDTO(tool_call_id="call-1", tool_name="send_mail"),
            TextDeltaEventDTO(text=" **Ada**"),
            TurnDoneEventDTO(text="Hello **Ada**"),
        ]

        first, second, end, form = await self.stream()

        text_selector = f"#djpa-reply-{self.turn.id}-text"
        assert (first.selector, first.mode) == (text_selector, "inner")
        assert first.elements == "<p>Hello</p>"
        assert second.elements == "<p>Hello <strong>Ada</strong></p>"
        self.assert_run_end(end)
        assert "djpa-line--assistant" in end.elements
        assert "<strong>Ada</strong>" in end.elements
        assert "disabled" not in form.elements
        assert ScriptedTransport.reads == ["0"]
        assert ScriptedTransport.closed == 1

    async def test_a_failed_run_shows_the_error_and_an_open_form(self):
        ScriptedTransport.script = [
            TextDeltaEventDTO(text="Hel"),
            TurnFailedEventDTO(error_code="model_api_error"),
        ]

        _text, end, form = await self.stream()

        self.assert_run_end(end)
        assert "djpa-line--error" in end.elements
        assert "model_api_error" in end.elements
        assert "Hel" not in end.elements
        assert "disabled" not in form.elements

    async def test_a_new_approval_stop_opens_a_new_stream(self):
        ScriptedTransport.script = [ApprovalRequestedEventDTO(approvals=(SEND_MAIL,))]

        (reconnect,) = await self.stream()

        assert reconnect.kind == "datastar-patch-signals"
        assert '"_djpaStream":' in reconnect.signals

    async def test_skips_the_events_of_an_earlier_stop(self):
        await PendingApproval.objects.acreate(
            turn_id=self.turn.id,
            tool_call_id="call-1",
            tool_name="send_mail",
            args_json="{}",
            decision=PendingApproval.Decision.APPROVED,
        )
        ScriptedTransport.script = [
            TextDeltaEventDTO(text="Old"),
            ApprovalRequestedEventDTO(approvals=(SEND_MAIL,)),
            TextDeltaEventDTO(text="New"),
            ApprovalRequestedEventDTO(approvals=(NEW_CALL,)),
        ]

        old, new, reconnect = await self.stream()

        assert old.elements == "<p>Old</p>"
        assert new.elements == "<p>New</p>"
        assert reconnect.kind == "datastar-patch-signals"
        assert ScriptedTransport.reads == ["0", "2"]
        assert ScriptedTransport.closed == 2  # noqa: PLR2004

    async def test_sends_a_keep_alive_when_no_event_comes(self):
        ScriptedTransport.script = [None, TurnDoneEventDTO(text="Hi")]

        keep_alive, end, _form = await self.stream()

        assert keep_alive.kind == "comment"
        self.assert_run_end(end)

    async def test_opens_a_new_stream_after_the_time_limit(self):
        ScriptedTransport.script = [TextDeltaEventDTO(text="Hi")]

        with mock.patch.object(views, "STREAM_SECONDS", SHORT_STREAM_SECONDS):
            text, reconnect = await self.stream()

        assert text.elements == "<p>Hi</p>"
        assert reconnect.kind == "datastar-patch-signals"
        assert ScriptedTransport.closed == 1

    async def test_a_done_turn_shows_the_reply_from_the_database(self):
        await self.set_turn(status=Turn.Status.DONE)

        end, form = await self.stream()

        self.assert_run_end(end)
        assert "<strong>Ada</strong>" in end.elements
        assert "disabled" not in form.elements
        assert ScriptedTransport.reads == []

    async def test_a_waiting_turn_shows_the_approval_cards(self):
        await self.set_turn(status=Turn.Status.WAITING_APPROVAL)
        approval = await PendingApproval.objects.acreate(
            turn_id=self.turn.id,
            tool_call_id="call-1",
            tool_name="send_mail",
            args_json='{"to":"ada"}',
        )

        end, form = await self.stream()

        self.assert_run_end(end)
        decide_url = reverse("dj_pydantic_agents:decide_approval", args=[approval.id])
        assert f"@post('{decide_url}'" in end.elements
        assert "X-CSRFToken" in end.elements
        assert "disabled" in form.elements

    async def test_a_stale_turn_fails_with_worker_lost(self):
        await self.set_turn(
            status_changed_at=timezone.now() - timedelta(seconds=STALE_SECONDS + 1),
        )

        end, _form = await self.stream()

        assert "worker_lost" in end.elements
        turn = await Turn.objects.aget(id=self.turn.id)
        assert turn.status == Turn.Status.FAILED

    async def test_another_user_gets_not_found(self):
        other = await User.objects.acreate(username="other", is_staff=True)
        await self.async_client.aforce_login(other)

        response = await self.async_client.get(
            reverse("dj_pydantic_agents:stream_turn", args=[self.turn.id]),
        )

        assert response.status_code == 404  # noqa: PLR2004

    async def test_a_user_who_is_not_logged_in_is_forbidden(self):
        response = await self.async_client.get(
            reverse("dj_pydantic_agents:stream_turn", args=[self.turn.id]),
        )

        assert response.status_code == 403  # noqa: PLR2004
