"""The public entry point of contrib.codex."""

from dj_pydantic_agents.contrib.codex.login_repository import PlanLoginRepository
from dj_pydantic_agents.contrib.codex.login_service import PlanLoginService


def build_plan_login_service() -> PlanLoginService:
    return PlanLoginService(repository=PlanLoginRepository())
