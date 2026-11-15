# dj-pydantic-agents

A reusable Django package for Pydantic AI agent turns, streaming and approvals. Many projects use it. Keep it free of project code.

## Layers

- `src/dj_pydantic_agents/kit/` is Layer 1. It imports no Django module and no project module. `tests/test_kit_boundary.py` checks this.
- The core app and `contrib/` are Layer 2. Imports go down only.
- The package never imports a project module. It reaches project code only through the dotted paths in the `DJ_PYDANTIC_AGENTS` setting.

## Rules

- The internal code follows the ff-dj rules: services, repositories and DTOs.
- Protocols exist only in `extensions.py`. Repositories stay concrete.
- The package keeps its own `InternalDTO` and `ExternalDTO`. A test checks that their configuration matches the house style.
- The package has its own composition root in `composition.py`. Do not register code in `AppConfig.ready()`.
  - One exception: `ready()` imports `checks.py`, because Django registers a system check when its module loads.
- The public API is the `build_*` functions in `composition.py`, the DTOs, the errors, the settings and the signals. The service and repository classes are private.
- `create_autospec()` reads the annotations of the class that it copies. So a class that a test autospecs imports its annotation types at runtime, with `# noqa: TC001`.

## Versions

- Python 3.14 or later. Django 6.0 or later.
- Pin `pydantic-ai-slim==2.68.*` and `pydantic-ai-harness==0.68.*`. They move together. A Pydantic AI upgrade is a new package release.
- `[tool.uv] exclude-newer-package` exempts the Pydantic AI packages from the 7-day `exclude-newer` window. Update it with each upgrade.

## Commands

- Start PostgreSQL and Redis for the tests: `docker compose up -d` (PostgreSQL on port 5433, Redis on port 6380).
- Install the extras for development: `uv sync --all-extras`.
- Tests: `uv run pytest`. Run them with the `run_test` tool.
- Lint and format: `uv run ruff check .` and `uv run ruff format .`.
- Types: `uv run mypy src tests`.
- A test of the views in a browser: the demo project in `tests/demo/`. The README section "The demo" has the commands. It needs an ASGI server, because `runserver` cannot stream.

## CI

- `.github/workflows/ci.yml` runs ruff, mypy and pytest on each push to `main` and on each pull request.
- The `locked` job tests the versions in `uv.lock`. The `lowest-direct` job tests the lowest versions that `pyproject.toml` lets in, for example Django 6.0.
- When you change a lower bound in `pyproject.toml`, the `lowest-direct` job tests it.
- Both jobs install each extra, so the jobs also test `contrib.celery`.
- `[tool.uv] exclude-newer` keeps `uv.lock` the same on each device and in CI. Do not remove it.
