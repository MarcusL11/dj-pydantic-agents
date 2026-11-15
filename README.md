# dj-pydantic-agents

Agent turns, streaming and approvals for Django. Not the same package as [`django-pydantic-ai`](https://github.com/hartungstenio/django-pydantic-ai), which stores memory and conversations.

## Status

Version 0.1 is in development. Do not use it in production.

## Needs

- Python 3.14 or later
- Django 6.0 or later
- PostgreSQL
- `pydantic-ai-slim==2.68.*` and `pydantic-ai-harness==0.68.*`

## Development

```bash
uv sync
docker compose up -d
uv run pytest
```

The test database runs in Docker on host port 5433.
