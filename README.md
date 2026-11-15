# dj-pydantic-agents

Agent turns, streaming and approvals for Django. Not the same package as [`django-pydantic-ai`](https://github.com/hartungstenio/django-pydantic-ai), which stores memory and conversations.

## Status

Version 0.1 is in development. Do not use it in production.

## Needs

- Python 3.14 or later
- Django 6.0 or later
- PostgreSQL
- `pydantic-ai-slim==2.68.*` and `pydantic-ai-harness==0.68.*`

## Celery

Install the extra: `dj-pydantic-agents[celery]`. Then add the app and the task runner:

```python
INSTALLED_APPS = [
    ...,
    "dj_pydantic_agents",
    "dj_pydantic_agents.contrib.celery",
]

DJ_PYDANTIC_AGENTS = {
    ...,
    "TASK_RUNNER": "dj_pydantic_agents.contrib.celery.runner.CeleryTaskRunner",
    "CELERY_QUEUE": "agents",  # Optional. The default is the default Celery queue.
}
```

The worker finds the turn task through `app.autodiscover_tasks()`. Without the app in `INSTALLED_APPS`, the worker does not know the task, and the check `dj_pydantic_agents.E006` fails.

The task uses the Celery time limits of the project. A turn can take more time than other tasks. To set the limits for the turn task only, use `CELERY_TASK_ANNOTATIONS`:

```python
CELERY_TASK_ANNOTATIONS = {
    "dj_pydantic_agents.run_turn": {"soft_time_limit": 600, "time_limit": 660},
}
```

## Development

```bash
uv sync --all-extras
docker compose up -d
uv run pytest
```

PostgreSQL runs in Docker on host port 5433, and Redis on host port 6380.
