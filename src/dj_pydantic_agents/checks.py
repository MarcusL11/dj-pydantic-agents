"""System checks: import each dotted path and compare it with its contract.

A wrong path then fails in manage.py check, not during a turn. The checks do
not call the extension objects, except SPECS.
"""

import inspect
from annotationlib import Format
from typing import TYPE_CHECKING
from typing import Any

from django.apps import apps
from django.core.checks import Error
from django.core.checks import register
from django.utils.module_loading import import_string

from dj_pydantic_agents.conf import SETTING_NAME
from dj_pydantic_agents.conf import missing_keys
from dj_pydantic_agents.conf import raw_settings
from dj_pydantic_agents.extensions import AgentPermission
from dj_pydantic_agents.extensions import DepsFactory
from dj_pydantic_agents.extensions import EventTransport
from dj_pydantic_agents.extensions import ModelFactory
from dj_pydantic_agents.extensions import ReplySanitizer
from dj_pydantic_agents.extensions import TaskRunner
from dj_pydantic_agents.kit.specs import AgentSpec
from dj_pydantic_agents.transports.redis_stream import RedisStreamTransport

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Mapping
    from collections.abc import Sequence

    from django.apps.config import AppConfig

CELERY_APP = "dj_pydantic_agents.contrib.celery"
CELERY_TASK_RUNNER = f"{CELERY_APP}.runner.CeleryTaskRunner"

# A method that the object must have: its name (None for a function), and the
# method of the Protocol with the keyword arguments of the contract.
type _Method = tuple[str | None, Callable[..., Any]]

_CONTRACTS: tuple[tuple[str, tuple[_Method, ...]], ...] = (
    ("DEPS_FACTORY", ((None, DepsFactory.__call__),)),
    ("MODEL_FACTORY", (("build", ModelFactory.build),)),
    ("PERMISSION", (("can_use", AgentPermission.can_use),)),
    (
        "EVENT_TRANSPORT",
        (("publish", EventTransport.publish), ("read", EventTransport.read)),
    ),
    ("SANITIZER", (("to_html", ReplySanitizer.to_html),)),
    ("TASK_RUNNER", (("enqueue", TaskRunner.enqueue),)),
)


@register()
def check_settings(
    app_configs: Sequence[AppConfig] | None = None,
    **kwargs: object,
) -> list[Error]:
    if missing := missing_keys():
        return [
            Error(
                f"{SETTING_NAME} needs these keys: {', '.join(missing)}.",
                id="dj_pydantic_agents.E001",
            ),
        ]
    configured = raw_settings() or {}
    errors = _spec_errors(configured["SPECS"])
    for key, methods in _CONTRACTS:
        path = configured.get(key)
        if path is not None:
            errors += _contract_errors(key=key, path=path, methods=methods)
    return errors + _redis_url_errors(configured) + _celery_app_errors(configured)


def _spec_errors(path: str) -> list[Error]:
    provider, errors = _import(key="SPECS", path=path)
    if provider is None:
        return errors
    try:
        specs = tuple(provider())
    except Exception as error:  # noqa: BLE001 - the check reports each error
        return [_error("E003", f"SPECS ({path}) failed: {error!r}.")]
    if not all(isinstance(spec, AgentSpec) for spec in specs):
        return [_error("E003", f"SPECS ({path}) must return AgentSpec items only.")]
    names = [spec.name for spec in specs]
    if duplicates := sorted({name for name in names if names.count(name) > 1}):
        return [_error("E003", f"SPECS has duplicate names: {', '.join(duplicates)}.")]
    return []


def _contract_errors(
    *,
    key: str,
    path: str,
    methods: tuple[_Method, ...],
) -> list[Error]:
    target, errors = _import(key=key, path=path)
    if target is None:
        return errors
    return [
        error
        for method, contract in methods
        for error in _method_errors(
            key=key,
            path=path,
            target=target,
            method=method,
            contract=contract,
        )
    ]


def _method_errors(
    *,
    key: str,
    path: str,
    target: Any,
    method: str | None,
    contract: Callable[..., Any],
) -> list[Error]:
    function = target if method is None else getattr(target, method, None)
    if function is None or not callable(function):
        return [_error("E004", f"{key} ({path}) has no {method}() method.")]
    if missing := _missing_keywords(function=function, contract=contract):
        return [
            _error(
                "E004",
                f"{key} ({path}) needs these keyword arguments: {', '.join(missing)}.",
            ),
        ]
    return []


def _redis_url_errors(configured: Mapping[str, Any]) -> list[Error]:
    try:
        transport = import_string(configured["EVENT_TRANSPORT"])
    except ImportError:
        return []
    uses_redis = isinstance(transport, type) and issubclass(
        transport,
        RedisStreamTransport,
    )
    if uses_redis and not configured.get("REDIS_URL"):
        return [_error("E005", "The Redis transport needs REDIS_URL.")]
    return []


def _celery_app_errors(configured: Mapping[str, Any]) -> list[Error]:
    # A string compare, so that the core app does not import celery.
    uses_celery = configured["TASK_RUNNER"] == CELERY_TASK_RUNNER
    if uses_celery and not apps.is_installed(CELERY_APP):
        return [
            _error(
                "E006",
                f"The Celery task runner needs {CELERY_APP} in INSTALLED_APPS.",
            ),
        ]
    return []


def _import(*, key: str, path: str) -> tuple[Any, list[Error]]:
    try:
        return import_string(path), []
    except ImportError as error:
        return None, [_error("E002", f"{key} ({path}) does not import: {error}.")]


def _missing_keywords(
    *,
    function: Callable[..., Any],
    contract: Callable[..., Any],
) -> tuple[str, ...]:
    # FORWARDREF: a project can import its annotation types for type checks only.
    parameters = _signature(function).parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        return ()
    return tuple(
        name
        for name, parameter in _signature(contract).parameters.items()
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY
        and (
            name not in parameters
            or parameters[name].kind is inspect.Parameter.POSITIONAL_ONLY
        )
    )


def _signature(function: Callable[..., Any]) -> inspect.Signature:
    return inspect.signature(function, annotation_format=Format.FORWARDREF)


def _error(code: str, message: str) -> Error:
    return Error(message, id=f"dj_pydantic_agents.{code}")
