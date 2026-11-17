"""The public entry points of the package. Each call builds a new service.

A project calls only these functions. The service and repository classes are
private. This is the only module that reads the settings and imports the
dotted paths of the extension points.
"""

from typing import TYPE_CHECKING
from typing import Any

from django.utils.module_loading import import_string
from pydantic_ai.usage import UsageLimits

from dj_pydantic_agents.conf import PackageSettings
from dj_pydantic_agents.conf import load_settings
from dj_pydantic_agents.files import AttachmentFileStore
from dj_pydantic_agents.kit.runner import TurnRunner
from dj_pydantic_agents.repositories.attachment_command_repository import (
    AttachmentCommandRepository,
)
from dj_pydantic_agents.repositories.conversation_query_repository import (
    ConversationQueryRepository,
)
from dj_pydantic_agents.repositories.turn_command_repository import (
    TurnCommandRepository,
)
from dj_pydantic_agents.services.attachment_command_service import (
    AttachmentCommandService,
)
from dj_pydantic_agents.services.attachment_command_service import AttachmentRules
from dj_pydantic_agents.services.conversation_command_service import (
    ConversationCommandService,
)
from dj_pydantic_agents.services.conversation_query_service import (
    ConversationQueryService,
)
from dj_pydantic_agents.services.turn_run_service import TurnRunService

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dj_pydantic_agents.dtos.turn_commands import UserId
    from dj_pydantic_agents.extensions import DepsFactory
    from dj_pydantic_agents.extensions import EventTransport
    from dj_pydantic_agents.extensions import ReplySanitizer
    from dj_pydantic_agents.kit.specs import AgentSpec


def build_conversation_command_service() -> ConversationCommandService:
    settings = load_settings()
    return ConversationCommandService(
        repository=TurnCommandRepository(),
        queries=ConversationQueryRepository(),
        specs=specs_by_name(settings.specs),
        permission=import_string(settings.permission)(),
        task_runner=import_string(settings.task_runner)(),
        files=_file_store(settings),
        stale_turn_seconds=settings.stale_turn_seconds,
        pending_attachment_seconds=settings.pending_attachment_seconds,
    )


def build_conversation_query_service() -> ConversationQueryService:
    settings = load_settings()
    return ConversationQueryService(
        repository=ConversationQueryRepository(),
        permission=import_string(settings.permission)(),
        files=_file_store(settings),
        pending_attachment_seconds=settings.pending_attachment_seconds,
    )


def build_attachment_command_service() -> AttachmentCommandService:
    settings = load_settings()
    return AttachmentCommandService(
        repository=AttachmentCommandRepository(),
        queries=ConversationQueryRepository(),
        files=_file_store(settings),
        specs=specs_by_name(settings.specs),
        permission=import_string(settings.permission)(),
        rules=AttachmentRules(
            media_types=tuple(settings.attachment_types),
            max_files=settings.attachment_max_files,
            max_file_bytes=settings.attachment_max_file_bytes,
            max_message_bytes=settings.attachment_max_message_bytes,
            pending_seconds=settings.pending_attachment_seconds,
        ),
    )


def build_turn_run_service() -> TurnRunService:
    """Only entry.run_turn() calls this. A project does not need it."""
    settings = load_settings()
    return TurnRunService(
        repository=TurnCommandRepository(),
        specs=specs_by_name(settings.specs),
        deps_factory=_deps_factory(settings.deps_factory),
        model_factory=import_string(settings.model_factory)(),
        transport=build_event_transport(),
        runner=TurnRunner(),
        files=_file_store(settings),
        attachment_history_turns=settings.attachment_history_turns,
        usage_limits=_usage_limits(settings.usage_limits),
    )


def build_event_transport() -> EventTransport:
    """The transport of EVENT_TRANSPORT. A stream view reads the events with it."""
    return import_string(load_settings().event_transport)()


def build_reply_sanitizer() -> ReplySanitizer:
    """The sanitiser of SANITIZER. It turns the Markdown of a reply into HTML."""
    return import_string(load_settings().sanitizer)()


def specs_by_name(path: str) -> dict[str, AgentSpec]:
    return {spec.name: spec for spec in import_string(path)()}


def _file_store(settings: PackageSettings) -> AttachmentFileStore:
    return AttachmentFileStore(storage_alias=settings.attachment_storage)


def _usage_limits(values: Mapping[str, Any] | None) -> UsageLimits | None:
    return None if values is None else UsageLimits(**values)


def _deps_factory(path: str | None) -> DepsFactory:
    if path is not None:
        return import_string(path)
    return _no_deps


def _no_deps(*, agent_name: str, user_id: UserId, conversation_id: str) -> None:
    return None
