"""The Celery task that runs one turn in a worker."""

from celery import shared_task

from dj_pydantic_agents import entry

TASK_NAME = "dj_pydantic_agents.run_turn"


@shared_task(name=TASK_NAME, ignore_result=True)
def run_turn_task(turn_id: str) -> None:
    """Run the turn. run_turn() records each failure, so the task does not retry.

    A second delivery of the task does nothing, because only a queued turn runs.
    """
    entry.run_turn(turn_id)
