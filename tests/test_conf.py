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

    @override_settings(DJ_PYDANTIC_AGENTS={"SPECS": "tests.fakes.build_specs"})
    def test_names_each_missing_key(self):
        with self.assertRaisesRegex(
            ImproperlyConfigured,
            "MODEL_FACTORY, EVENT_TRANSPORT, TASK_RUNNER",
        ):
            load_settings()
