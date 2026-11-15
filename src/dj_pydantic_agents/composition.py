"""The public entry points of the package. Each call builds a new service.

A project calls only these functions. The service and repository classes are
private. This is the only module that reads the settings and imports the
dotted paths of the extension points.
"""

from typing import TYPE_CHECKING

from django.utils.module_loading import import_string

from dj_pydantic_agents.conf import load_settings
from dj_pydantic_agents.kit.runner import TurnRunner
from dj_pydantic_agents.repositories.conversation_query_repository import (
    ConversationQueryRepository,
)
from dj_pydantic_agents.repositories.turn_command_repository import (
    TurnCommandRepository,
)
from dj_pydantic_agents.services.conversation_command_service import (
    ConversationCommandService,
)
from dj_pydantic_agents.services.conversation_query_service import (
    ConversationQueryService,
)
from dj_pydantic_agents.services.turn_run_service import TurnRunService

if TYPE_CHECKING:
    from dj_pydantic_agents.dtos.turn_commands import UserId
    from dj_pydantic_agents.extensions import DepsFactory
    from dj_pydantic_agents.kit.specs import AgentSpec


def build_conversation_command_service() -> ConversationCommandService:
    settings = load_settings()
    return ConversationCommandService(
        repository=TurnCommandRepository(),
        queries=ConversationQueryRepository(),
        specs=specs_by_name(settings.specs),
        permission=import_string(settings.permission)(),
        task_runner=import_string(settings.task_runner)(),
    )


def build_conversation_query_service() -> ConversationQueryService:
    settings = load_settings()
    return ConversationQueryService(
        repository=ConversationQueryRepository(),
        permission=import_string(settings.permission)(),
    )


def build_turn_run_service() -> TurnRunService:
    """Only entry.run_turn() calls this. A project does not need it."""
    settings = load_settings()
    return TurnRunService(
        repository=TurnCommandRepository(),
        specs=specs_by_name(settings.specs),
        deps_factory=_deps_factory(settings.deps_factory),
        model_factory=import_string(settings.model_factory)(),
        transport=import_string(settings.event_transport)(),
        runner=TurnRunner(),
    )


def specs_by_name(path: str) -> dict[str, AgentSpec]:
    return {spec.name: spec for spec in import_string(path)()}


def _deps_factory(path: str | None) -> DepsFactory:
    if path is not None:
        return import_string(path)
    return _no_deps


def _no_deps(*, agent_name: str, user_id: UserId, conversation_id: str) -> None:
    return None
