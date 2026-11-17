"""The Celery tasks: run one turn, and delete the expired pending files."""

from celery import shared_task

from dj_pydantic_agents import entry

TASK_NAME = "dj_pydantic_agents.run_turn"
DELETE_PENDING_ATTACHMENTS_TASK_NAME = "dj_pydantic_agents.delete_pending_attachments"


@shared_task(name=TASK_NAME, ignore_result=True)
def run_turn_task(turn_id: str) -> None:
    """Run the turn. run_turn() records each failure, so the task does not retry.

    A second delivery of the task does nothing, because only a queued turn runs.
    """
    entry.run_turn(turn_id)


@shared_task(name=DELETE_PENDING_ATTACHMENTS_TASK_NAME, ignore_result=True)
def delete_pending_attachments_task() -> None:
    """Delete the expired pending files. Schedule it, for example each hour."""
    entry.delete_expired_attachments()
