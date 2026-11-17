from unittest import mock

from django.contrib.auth.models import User
from django.urls import reverse

from dj_pydantic_agents.models import Conversation
from dj_pydantic_agents.models import PendingApproval
from dj_pydantic_agents.models import Turn
from tests.contrib.datastar.forms import form_is_closed
from tests.contrib.datastar.sse import read_patches
from tests.factories import ConversationFactory
from tests.factories import PendingApprovalFactory
from tests.factories import TurnFactory
from tests.factories import UserFactory
from tests.fakes import FakeTaskRunner
from tests.testcases import TestCase

TRANSCRIPT = "#djpa-transcript"


class TestSendMessage(TestCase):
    owner: User
    other: User
    conversation: Conversation

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create(is_staff=True)
        cls.other = UserFactory.create(is_staff=True)
        cls.conversation = ConversationFactory.create(owner=cls.owner)

    def setUp(self):
        FakeTaskRunner.reset()

    def url(self, conversation_id=None):
        return reverse(
            "dj_pydantic_agents:send_message",
            args=[conversation_id or self.conversation.id],
        )

    async def send(self, prompt="Hi", *, user=None, conversation_id=None):
        await self.async_client.aforce_login(user or self.owner)
        return await self.async_client.post(
            self.url(conversation_id),
            {"prompt": prompt},
        )

    async def test_shows_the_message_a_streaming_reply_and_a_closed_form(self):
        response = await self.send("Mail *Ada*")

        assert response.status_code == 200  # noqa: PLR2004
        turn = await Turn.objects.aget(conversation_id=self.conversation.id)
        assert FakeTaskRunner.turn_ids == [turn.id]
        line, reply, form = await read_patches(response)
        assert (line.selector, line.mode) == (TRANSCRIPT, "append")
        assert "djpa-line--user" in line.elements
        assert "Mail *Ada*" in line.elements
        assert (reply.selector, reply.mode) == (TRANSCRIPT, "append")
        assert f'id="djpa-reply-{turn.id}"' in reply.elements
        stream_url = reverse("dj_pydantic_agents:stream_turn", args=[turn.id])
        assert f"@get('{stream_url}'" in reply.elements
        assert (form.selector, form.mode) == ("#djpa-message-form", "replace")
        assert form_is_closed(form.elements)

    async def test_a_failed_enqueue_shows_the_error_and_an_open_form(self):
        with mock.patch.object(
            FakeTaskRunner,
            "enqueue",
            side_effect=ConnectionError("No broker"),
        ):
            response = await self.send()

        assert response.status_code == 200  # noqa: PLR2004
        turn = await Turn.objects.aget(conversation_id=self.conversation.id)
        assert turn.error_code == "enqueue_failed"
        line, error, form = await read_patches(response)
        assert "djpa-line--user" in line.elements
        assert "djpa-line--error" in error.elements
        assert "enqueue_failed" in error.elements
        assert not form_is_closed(form.elements)

    async def test_an_empty_message_is_a_bad_request(self):
        response = await self.send("   ")

        assert response.status_code == 400  # noqa: PLR2004

    async def test_a_message_during_a_turn_is_a_conflict(self):
        await self.send()

        response = await self.send()

        assert response.status_code == 409  # noqa: PLR2004

    async def test_another_user_gets_not_found(self):
        response = await self.send(user=self.other)

        assert response.status_code == 404  # noqa: PLR2004

    async def test_a_user_who_is_not_staff_is_forbidden(self):
        await User.objects.filter(pk=self.owner.pk).aupdate(is_staff=False)

        response = await self.send()

        assert response.status_code == 403  # noqa: PLR2004

    async def test_a_user_who_is_not_logged_in_is_forbidden(self):
        response = await self.async_client.post(self.url(), {"prompt": "Hi"})

        assert response.status_code == 403  # noqa: PLR2004

    async def test_a_get_is_not_allowed(self):
        await self.async_client.aforce_login(self.owner)

        response = await self.async_client.get(self.url())

        assert response.status_code == 405  # noqa: PLR2004


class TestDecideApproval(TestCase):
    owner: User
    turn: Turn
    first: PendingApproval
    second: PendingApproval

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory.create(is_staff=True)
        cls.turn = TurnFactory.create(
            conversation=ConversationFactory.create(owner=cls.owner),
            requested_by=cls.owner,
            status=Turn.Status.WAITING_APPROVAL,
        )
        cls.first = PendingApprovalFactory.create(turn=cls.turn)
        cls.second = PendingApprovalFactory.create(turn=cls.turn)

    def setUp(self):
        FakeTaskRunner.reset()

    async def decide(self, approval, approved="true"):
        await self.async_client.aforce_login(self.owner)
        return await self.async_client.post(
            reverse("dj_pydantic_agents:decide_approval", args=[approval.id]),
            {"approved": approved},
        )

    async def test_a_first_decision_shows_only_the_decision(self):
        response = await self.decide(self.first, approved="false")

        assert response.status_code == 200  # noqa: PLR2004
        (decision,) = await read_patches(response)
        assert f'id="djpa-approval-{self.first.id}-actions"' in decision.elements
        assert "Denied" in decision.elements
        assert FakeTaskRunner.turn_ids == []

    async def test_the_last_decision_shows_a_streaming_reply(self):
        await self.decide(self.first)

        response = await self.decide(self.second)

        decision, reply = await read_patches(response)
        assert "Approved" in decision.elements
        assert (reply.selector, reply.mode) == (TRANSCRIPT, "append")
        assert f'id="djpa-reply-{self.turn.id}"' in reply.elements
        assert FakeTaskRunner.turn_ids == [self.turn.id]

    async def test_a_second_decision_is_a_conflict(self):
        await self.decide(self.first)

        response = await self.decide(self.first)

        assert response.status_code == 409  # noqa: PLR2004

    async def test_a_bad_decision_is_a_bad_request(self):
        response = await self.decide(self.first, approved="maybe")

        assert response.status_code == 400  # noqa: PLR2004
