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

## Versions

- Python 3.14 or later. Django 6.0 or later.
- Pin `pydantic-ai-slim==2.68.*` and `pydantic-ai-harness==0.68.*`. They move together. A Pydantic AI upgrade is a new package release.
- `[tool.uv] exclude-newer-package` exempts the Pydantic AI packages from the 7-day `exclude-newer` window of the device. Update it with each upgrade.

## Commands

- Start the test database: `docker compose up -d` (PostgreSQL on port 5433).
- Tests: `uv run pytest`. Run them with the `run_test` tool.
- Lint and format: `uv run ruff check .` and `uv run ruff format .`.
- Types: `uv run mypy src tests`.
