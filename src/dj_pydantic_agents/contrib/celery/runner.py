"""Send each turn to a Celery worker after the transaction commits."""

from functools import partial

from django.db import transaction

from dj_pydantic_agents.conf import load_settings
from dj_pydantic_agents.contrib.celery.tasks import run_turn_task


class CeleryTaskRunner:
    """TASK_RUNNER for Celery. CELERY_QUEUE selects the queue.

    The services call enqueue() when no transaction is open. Then on_commit()
    sends the task at once, and a broker error goes to the service, which
    fails the turn with enqueue_failed. Inside an open atomic() block, the
    task goes at the commit. A broker error there leaves the turn in the queue.
    """

    def __init__(self) -> None:
        queue = load_settings().celery_queue
        self._options = {"queue": queue} if queue else {}

    def enqueue(self, *, turn_id: str) -> None:
        transaction.on_commit(
            partial(run_turn_task.apply_async, args=(turn_id,), **self._options),
        )
