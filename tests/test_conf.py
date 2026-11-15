from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from dj_pydantic_agents.conf import load_settings
from tests.testcases import SimpleTestCase


class TestLoadSettings(SimpleTestCase):
    def test_applies_the_defaults(self):
        settings = load_settings()

        assert settings.specs == "tests.fakes.build_specs"
        assert settings.deps_factory is None
        assert settings.model_names == {}
        assert settings.permission == "dj_pydantic_agents.permissions.StaffPermission"
        assert settings.sanitizer == (
            "dj_pydantic_agents.rendering.nh3_sanitizer.Nh3Sanitizer"
        )

    @override_settings(
        DJ_PYDANTIC_AGENTS={
            "SPECS": "tests.fakes.build_specs",
            "MODEL_FACTORY": "tests.fakes.FakeModelFactory",
            "EVENT_TRANSPORT": "tests.fakes.FakeTransport",
            "TASK_RUNNER": "tests.fakes.FakeTaskRunner",
        },
    )
    def test_redis_url_has_no_default(self):
        assert load_settings().redis_url is None

    @override_settings(DJ_PYDANTIC_AGENTS={"SPECS": "tests.fakes.build_specs"})
    def test_names_each_missing_key(self):
        with self.assertRaisesRegex(
            ImproperlyConfigured,
            "MODEL_FACTORY, EVENT_TRANSPORT, TASK_RUNNER",
        ):
            load_settings()
