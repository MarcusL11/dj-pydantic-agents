import subprocess
import sys

from tests.testcases import SimpleTestCase

_CHECK_KIT_IMPORTS = """
import importlib
import pkgutil
import sys

import dj_pydantic_agents.kit as kit

for module in pkgutil.walk_packages(kit.__path__, prefix="dj_pydantic_agents.kit."):
    importlib.import_module(module.name)
names = [n for n in sys.modules if n == "django" or n.startswith("django.")]
print(",".join(names))
sys.exit(1 if names else 0)
"""


class TestKitBoundary(SimpleTestCase):
    def test_kit_imports_no_django_module(self):
        # pytest-django imports Django in this process, so check in a new interpreter.
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-I", "-c", _CHECK_KIT_IMPORTS],
            capture_output=True,
            check=False,
            text=True,
        )

        assert result.returncode == 0, result.stdout + result.stderr
