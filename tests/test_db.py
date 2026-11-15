import asyncio
import threading

from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.db import connection
from django.db import transaction

from dj_pydantic_agents.db import database_sync_to_async
from tests.testcases import SimpleTestCase
from tests.testcases import TestCase
from tests.testcases import TransactionTestCase

WAIT_SECONDS = 5


def count_users() -> int:
    return User.objects.count()


class TestDatabaseSyncToAsyncConnections(TransactionTestCase):
    def test_closes_the_connection_after_the_call(self):
        count = async_to_sync(database_sync_to_async(count_users))()

        assert count == 0
        assert connection.connection is None


class TestDatabaseSyncToAsyncTransaction(TestCase):
    def test_keeps_a_connection_inside_a_transaction(self):
        with transaction.atomic():
            async_to_sync(database_sync_to_async(count_users))()

            assert connection.connection is not None


class TestDatabaseSyncToAsyncCancel(SimpleTestCase):
    def test_returns_the_result(self):
        result = async_to_sync(database_sync_to_async(lambda a, *, b: a + b))(1, b=2)

        assert result == 1 + 2

    def test_raises_the_error_of_the_function(self):
        def fail() -> None:
            msg = "boom"
            raise ValueError(msg)

        with self.assertRaises(ValueError):
            async_to_sync(database_sync_to_async(fail))()

    async def test_a_cancel_waits_until_the_function_returns(self):
        started = threading.Event()
        release = threading.Event()
        finished: list[bool] = []

        def work() -> None:
            started.set()
            release.wait(WAIT_SECONDS)
            finished.append(True)

        task = asyncio.create_task(database_sync_to_async(work)())
        await asyncio.to_thread(started.wait, WAIT_SECONDS)
        task.cancel()
        await asyncio.sleep(0.05)

        assert not task.done()

        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        assert finished == [True]
