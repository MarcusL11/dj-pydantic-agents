"""Call sync database code from async code, and free the connection after it.

An async view or a stream holds its request for a long time. Django closes the
connections of a request only at the end of the request. So this helper closes
them before and after each call.
"""

import asyncio
from functools import partial
from functools import wraps
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from django.db import connections

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Coroutine


def database_sync_to_async[**P, T](
    function: Callable[P, T],
) -> Callable[P, Coroutine[None, None, T]]:
    """Run the function in the sync thread of the request.

    A cancellation waits until the function returns, then goes on. So a
    cancelled stream cannot leave a thread with an open transaction.
    """

    @wraps(function)
    async def call(*args: P.args, **kwargs: P.kwargs) -> T:
        run = sync_to_async(_run_and_close, thread_sensitive=True)
        task = asyncio.create_task(run(partial(function, *args, **kwargs)))
        return await _complete(task)

    return call


def _run_and_close[T](function: Callable[[], T]) -> T:
    _close_open_connections()
    try:
        return function()
    finally:
        _close_open_connections()


def _close_open_connections() -> None:
    """Close each open connection of this thread that is not in a transaction.

    Not close_old_connections(): it can open a connection to check it.
    """
    for connection in connections.all(initialized_only=True):
        if connection.connection is not None and not connection.in_atomic_block:
            connection.close()


async def _complete[T](task: asyncio.Task[T]) -> T:
    cancellation: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as error:
            cancellation = error
        except Exception:  # noqa: BLE001 - task.result() raises it again
            break
    if cancellation is not None:
        if not task.cancelled():
            # Mark an error as read, so that asyncio does not log it.
            task.exception()
        raise cancellation
    return task.result()
