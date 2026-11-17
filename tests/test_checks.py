from typing import TYPE_CHECKING

from django.conf import settings
from django.test import modify_settings
from django.test import override_settings
from unittest_parametrize import param
from unittest_parametrize import parametrize

from dj_pydantic_agents.checks import check_settings
from dj_pydantic_agents.kit.specs import AgentSpec
from tests.testcases import SimpleTestCase

if TYPE_CHECKING:
    from dj_pydantic_agents.dtos.turn_commands import UserId


def failing_specs() -> tuple[AgentSpec, ...]:
    raise RuntimeError


def text_specs() -> tuple[str, ...]:
    return ("assistant",)


def duplicate_specs() -> tuple[AgentSpec, ...]:
    spec = AgentSpec(name="assistant", instructions="")
    return (spec, spec)


class NoEnqueue:
    pass


class PositionalRunner:
    def enqueue(self, turn_id: str, /) -> None:
        pass


class KeywordsRunner:
    def enqueue(self, **kwargs: object) -> None:
        pass


class PublishOnlyTransport:
    def publish(self, *, turn_id: str, event: object) -> str:
        return "1-0"


class WrongKeywordSanitizer:
    def to_html(self, *, markdown: str) -> str:
        return markdown


def deps_without_conversation(*, agent_name: str, user_id: UserId) -> None:
    pass


CELERY_APP = "dj_pydantic_agents.contrib.celery"
CELERY_RUNNER = f"{CELERY_APP}.runner.CeleryTaskRunner"
REDIS_TRANSPORT = "dj_pydantic_agents.transports.redis_stream.RedisStreamTransport"


def with_keys(**overrides: object) -> dict[str, object]:
    return {**settings.DJ_PYDANTIC_AGENTS, **overrides}


class TestCheckSettings(SimpleTestCase):
    def check_ids(self) -> list[str | None]:
        return [error.id for error in check_settings()]

    def test_the_test_settings_pass(self):
        assert check_settings() == []

    @override_settings(DJ_PYDANTIC_AGENTS=None)
    def test_a_missing_setting_is_an_error(self):
        assert self.check_ids() == ["dj_pydantic_agents.E001"]

    @parametrize(
        ("overrides", "error_id"),
        [
            param({"TASK_RUNNER": ""}, "E001", id="missing_key"),
            param({"TASK_RUNNER": "tests.nothing.Runner"}, "E002", id="bad_path"),
            param({"SPECS": "tests.test_checks.failing_specs"}, "E003", id="fails"),
            param({"SPECS": "tests.test_checks.text_specs"}, "E003", id="not_specs"),
            param(
                {"SPECS": "tests.test_checks.duplicate_specs"},
                "E003",
                id="duplicates",
            ),
            param({"TASK_RUNNER": "tests.test_checks.NoEnqueue"}, "E004", id="method"),
            param(
                {"TASK_RUNNER": "tests.test_checks.PositionalRunner"},
                "E004",
                id="positional",
            ),
            param(
                {"DEPS_FACTORY": "tests.test_checks.deps_without_conversation"},
                "E004",
                id="keyword",
            ),
            param(
                {"EVENT_TRANSPORT": "tests.test_checks.PublishOnlyTransport"},
                "E004",
                id="no_read",
            ),
            param(
                {"SANITIZER": "tests.test_checks.WrongKeywordSanitizer"},
                "E004",
                id="sanitizer",
            ),
            param(
                {"EVENT_TRANSPORT": REDIS_TRANSPORT, "REDIS_URL": None},
                "E005",
                id="no_redis_url",
            ),
            param({"USAGE_LIMITS": {"requests": 60}}, "E007", id="usage_key"),
            param({"USAGE_LIMITS": [60]}, "E007", id="usage_type"),
            param({"ATTACHMENT_TYPES": ("text/html",)}, "E008", id="attachment_type"),
            param({"ATTACHMENT_STORAGE": "private"}, "E009", id="attachment_storage"),
        ],
    )
    def test_reports_a_wrong_extension_point(self, overrides, error_id):
        with override_settings(DJ_PYDANTIC_AGENTS=with_keys(**overrides)):
            assert self.check_ids() == [f"dj_pydantic_agents.{error_id}"]

    def test_no_attachment_types_need_no_storage(self):
        values = with_keys(ATTACHMENT_TYPES=(), ATTACHMENT_STORAGE="private")

        with override_settings(DJ_PYDANTIC_AGENTS=values):
            assert check_settings() == []

    def test_accepts_usage_limits(self):
        values = with_keys(USAGE_LIMITS={"request_limit": 60})

        with override_settings(DJ_PYDANTIC_AGENTS=values):
            assert check_settings() == []

    def test_accepts_keyword_arguments_by_name_or_by_kwargs(self):
        runner = "tests.test_checks.KeywordsRunner"

        with override_settings(DJ_PYDANTIC_AGENTS=with_keys(TASK_RUNNER=runner)):
            assert check_settings() == []

    def test_accepts_the_redis_transport_with_a_redis_url(self):
        values = with_keys(EVENT_TRANSPORT=REDIS_TRANSPORT)

        with override_settings(DJ_PYDANTIC_AGENTS=values):
            assert check_settings() == []

    def test_a_bad_transport_path_is_one_error(self):
        values = with_keys(EVENT_TRANSPORT="tests.nothing.Transport")

        with override_settings(DJ_PYDANTIC_AGENTS=values):
            assert self.check_ids() == ["dj_pydantic_agents.E002"]

    def test_the_celery_runner_needs_the_celery_app(self):
        values = with_keys(TASK_RUNNER=CELERY_RUNNER)

        with (
            override_settings(DJ_PYDANTIC_AGENTS=values),
            modify_settings(INSTALLED_APPS={"remove": [CELERY_APP]}),
        ):
            assert self.check_ids() == ["dj_pydantic_agents.E006"]

    def test_accepts_the_celery_runner_with_the_celery_app(self):
        values = with_keys(TASK_RUNNER=CELERY_RUNNER)

        with override_settings(DJ_PYDANTIC_AGENTS=values):
            assert check_settings() == []
