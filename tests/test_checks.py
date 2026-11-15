from typing import TYPE_CHECKING

from django.conf import settings
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


def deps_without_conversation(*, agent_name: str, user_id: UserId) -> None:
    pass


def with_keys(**overrides: str | None) -> dict[str, str | None]:
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
        ],
    )
    def test_reports_a_wrong_extension_point(self, overrides, error_id):
        with override_settings(DJ_PYDANTIC_AGENTS=with_keys(**overrides)):
            assert self.check_ids() == [f"dj_pydantic_agents.{error_id}"]

    def test_accepts_keyword_arguments_by_name_or_by_kwargs(self):
        runner = "tests.test_checks.KeywordsRunner"

        with override_settings(DJ_PYDANTIC_AGENTS=with_keys(TASK_RUNNER=runner)):
            assert check_settings() == []
