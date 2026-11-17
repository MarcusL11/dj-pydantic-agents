from unittest import mock

from django.conf import settings
from django.test import override_settings
from kombu.exceptions import OperationalError

import tests.celery_app  # noqa: F401 - the Celery app that runs the tasks
from dj_pydantic_agents.composition import build_conversation_command_service
from dj_pydantic_agents.contrib.celery import tasks
from dj_pydantic_agents.contrib.celery.runner import CeleryTaskRunner
from dj_pydantic_agents.contrib.celery.tasks import DELETE_PENDING_ATTACHMENTS_TASK_NAME
from dj_pydantic_agents.contrib.celery.tasks import TASK_NAME
from dj_pydantic_agents.contrib.celery.tasks import delete_pending_attachments_task
from dj_pydantic_agents.contrib.celery.tasks import run_turn_task
from dj_pydantic_agents.dtos.turn_commands import CreateConversationCommandDTO
from dj_pydantic_agents.dtos.turn_commands import StartTurnCommandDTO
from dj_pydantic_agents.errors import TurnNotQueued
from dj_pydantic_agents.kit.events import TurnDoneEventDTO
from dj_pydantic_agents.models import Turn
from tests.factories import UserFactory
from tests.fakes import FakeTransport
from tests.testcases import SimpleTestCase
from tests.testcases import TestCase
from tests.testcases import TransactionTestCase

CELERY_RUNNER = "dj_pydantic_agents.contrib.celery.runner.CeleryTaskRunner"


def with_keys(**overrides: str | None) -> dict[str, str | None]:
    return {**settings.DJ_PYDANTIC_AGENTS, **overrides}


class TestCeleryTaskRunner(TestCase):
    def setUp(self):
        self.apply_async = self.enterContext(
            mock.patch.object(run_turn_task, "apply_async", autospec=True),
        )

    def test_sends_the_task_after_the_commit(self):
        with self.captureOnCommitCallbacks() as callbacks:
            CeleryTaskRunner().enqueue(turn_id="trn_1")
        self.apply_async.assert_not_called()

        (callback,) = callbacks
        callback()

        self.apply_async.assert_called_once_with(args=("trn_1",))

    @override_settings(DJ_PYDANTIC_AGENTS=with_keys(CELERY_QUEUE="agents"))
    def test_sends_the_task_to_the_celery_queue(self):
        with self.captureOnCommitCallbacks(execute=True):
            CeleryTaskRunner().enqueue(turn_id="trn_1")

        self.apply_async.assert_called_once_with(args=("trn_1",), queue="agents")


class TestRunTurnTask(SimpleTestCase):
    def test_runs_the_turn(self):
        with mock.patch.object(tasks.entry, "run_turn", autospec=True) as run_turn:
            run_turn_task("trn_1")

        run_turn.assert_called_once_with("trn_1")
        assert run_turn_task.name == TASK_NAME


@override_settings(DJ_PYDANTIC_AGENTS=with_keys(TASK_RUNNER=CELERY_RUNNER))
class TestCeleryTurnFlow(TransactionTestCase):
    """No transaction is open, as in a project view. Eager mode runs the task."""

    def setUp(self):
        FakeTransport.reset()
        self.owner = UserFactory.create(is_staff=True)
        self.commands = build_conversation_command_service()
        self.conversation = self.commands.create_conversation(
            command=CreateConversationCommandDTO(
                owner_id=self.owner.pk,
                agent_name="assistant",
            ),
        )

    def start_turn(self):
        return self.commands.start_turn(
            command=StartTurnCommandDTO(
                conversation_id=self.conversation.conversation_id,
                user_id=self.owner.pk,
                prompt="Hi",
            ),
        )

    def test_a_worker_runs_the_turn(self):
        started = self.start_turn()

        turn = Turn.objects.get(id=started.turn_id)
        assert turn.status == Turn.Status.DONE
        assert FakeTransport.events[-1] == (
            started.turn_id,
            TurnDoneEventDTO(text="Hello"),
        )

    def test_a_broker_error_fails_the_turn(self):
        error = OperationalError("The broker is down.")

        with (
            mock.patch.object(run_turn_task, "apply_async", side_effect=error),
            self.assertRaises(TurnNotQueued) as raised,
        ):
            self.start_turn()

        assert raised.exception.__cause__ is error
        turn = Turn.objects.get(conversation_id=self.conversation.conversation_id)
        assert turn.status == Turn.Status.FAILED
        assert turn.error_code == "enqueue_failed"


class TestDeletePendingAttachmentsTask(SimpleTestCase):
    def test_the_task_deletes_the_expired_files(self):
        with mock.patch.object(
            tasks.entry,
            "delete_expired_attachments",
            autospec=True,
        ) as delete:
            delete_pending_attachments_task.delay()

        delete.assert_called_once_with()
        assert (
            delete_pending_attachments_task.name == DELETE_PENDING_ATTACHMENTS_TASK_NAME
        )
