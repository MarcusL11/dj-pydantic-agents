"""Read the DJ_PYDANTIC_AGENTS setting and apply the defaults."""

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    from collections.abc import Mapping
    from collections.abc import Sequence

SETTING_NAME = "DJ_PYDANTIC_AGENTS"

# The project must set these keys. Each value is a dotted path.
REQUIRED_KEYS = ("SPECS", "MODEL_FACTORY", "EVENT_TRANSPORT", "TASK_RUNNER")

DEFAULTS: Mapping[str, Any] = {
    "DEPS_FACTORY": None,
    "MODEL_NAMES": {},
    "PERMISSION": "dj_pydantic_agents.permissions.StaffPermission",
    "SANITIZER": "dj_pydantic_agents.rendering.nh3_sanitizer.Nh3Sanitizer",
    # The Redis transport needs it. The E005 check finds a missing value.
    "REDIS_URL": None,
    # The Celery queue of the turn task. None selects the default queue.
    "CELERY_QUEUE": None,
    # A queued or running turn with no change for this time has lost its worker.
    # Make it longer than the hard time limit of the turn task.
    "STALE_TURN_SECONDS": 1800,
    # The Fernet keys of contrib.codex. The first key encrypts, each key decrypts.
    "CODEX_TOKEN_KEYS": (),
    # The keyword arguments of pydantic_ai.usage.UsageLimits for one run of a
    # turn, for example {"request_limit": 60}. None sets no limit.
    "USAGE_LIMITS": None,
    # The storage alias of the attachment files. Use private storage.
    "ATTACHMENT_STORAGE": "default",
    # The media types that the chat takes. Empty: the chat takes no files.
    "ATTACHMENT_TYPES": (),
    # The limits of the files of one message.
    "ATTACHMENT_MAX_FILES": 5,
    "ATTACHMENT_MAX_FILE_BYTES": 10 * 1024 * 1024,
    "ATTACHMENT_MAX_MESSAGE_BYTES": 20 * 1024 * 1024,
    # The model gets the files of this number of latest turns, with the current turn.
    "ATTACHMENT_HISTORY_TURNS": 2,
    # An unsent file expires after this time. The cleanup task deletes it.
    "PENDING_ATTACHMENT_SECONDS": 3600,
}


@dataclass(frozen=True, kw_only=True)
class PackageSettings:
    specs: str
    deps_factory: str | None
    model_factory: str
    model_names: Mapping[str, str]
    permission: str
    event_transport: str
    task_runner: str
    sanitizer: str
    redis_url: str | None
    celery_queue: str | None
    stale_turn_seconds: int
    codex_token_keys: Sequence[str]
    usage_limits: Mapping[str, Any] | None
    attachment_storage: str
    attachment_types: Sequence[str]
    attachment_max_files: int
    attachment_max_file_bytes: int
    attachment_max_message_bytes: int
    attachment_history_turns: int
    pending_attachment_seconds: int


def raw_settings() -> Mapping[str, Any] | None:
    return getattr(settings, SETTING_NAME, None)


def missing_keys() -> tuple[str, ...]:
    configured = raw_settings() or {}
    return tuple(key for key in REQUIRED_KEYS if not configured.get(key))


def load_settings() -> PackageSettings:
    """Read the setting on each call, so that override_settings works."""
    if missing := missing_keys():
        msg = f"{SETTING_NAME} needs these keys: {', '.join(missing)}."
        raise ImproperlyConfigured(msg)
    values = {**DEFAULTS, **(raw_settings() or {})}
    return PackageSettings(
        specs=values["SPECS"],
        deps_factory=values["DEPS_FACTORY"],
        model_factory=values["MODEL_FACTORY"],
        model_names=values["MODEL_NAMES"],
        permission=values["PERMISSION"],
        event_transport=values["EVENT_TRANSPORT"],
        task_runner=values["TASK_RUNNER"],
        sanitizer=values["SANITIZER"],
        redis_url=values["REDIS_URL"],
        celery_queue=values["CELERY_QUEUE"],
        stale_turn_seconds=values["STALE_TURN_SECONDS"],
        codex_token_keys=values["CODEX_TOKEN_KEYS"],
        usage_limits=values["USAGE_LIMITS"],
        attachment_storage=values["ATTACHMENT_STORAGE"],
        attachment_types=tuple(values["ATTACHMENT_TYPES"]),
        attachment_max_files=values["ATTACHMENT_MAX_FILES"],
        attachment_max_file_bytes=values["ATTACHMENT_MAX_FILE_BYTES"],
        attachment_max_message_bytes=values["ATTACHMENT_MAX_MESSAGE_BYTES"],
        attachment_history_turns=values["ATTACHMENT_HISTORY_TURNS"],
        pending_attachment_seconds=values["PENDING_ATTACHMENT_SECONDS"],
    )
