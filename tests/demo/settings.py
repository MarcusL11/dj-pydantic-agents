"""Settings of the demo project. It is for a test in a browser only.

Start it with an ASGI server, because runserver cannot stream:

    uv run django-admin migrate --settings=tests.demo.settings --pythonpath=.
    uv run --with uvicorn uvicorn tests.demo.asgi:application --port 8001

With DJPA_DEMO_CODEX=1, the turns use the ChatGPT plan of the demo user.
DJPA_DEMO_MODEL selects the model. The default is the model of the paid plans.
"""

import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

from tests.settings import *  # noqa: F403

BASE_DIR = Path(__file__).parent
REDIS_TRANSPORT = "dj_pydantic_agents.transports.redis_stream.RedisStreamTransport"
CODEX_MODEL_FACTORY = "dj_pydantic_agents.contrib.codex.model_factory.CodexModelFactory"
# The saved tokens must decrypt after a restart, so the key stays in a file.
TOKEN_KEY_FILE = Path(tempfile.gettempdir()) / "djpa-demo-fernet.key"


def _token_key() -> str:
    if not TOKEN_KEY_FILE.exists():
        TOKEN_KEY_FILE.write_text(Fernet.generate_key().decode())
        TOKEN_KEY_FILE.chmod(0o600)
    return TOKEN_KEY_FILE.read_text().strip()


DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
ROOT_URLCONF = "tests.demo.urls"
TEMPLATES[0]["DIRS"] = [BASE_DIR / "templates"]  # noqa: F405

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

DJ_PYDANTIC_AGENTS = {
    "SPECS": "tests.fakes.build_specs",
    "MODEL_FACTORY": "tests.demo.agents.DemoModelFactory",
    "EVENT_TRANSPORT": REDIS_TRANSPORT,
    "TASK_RUNNER": "tests.demo.agents.ThreadTaskRunner",
    "REDIS_URL": os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
    "CODEX_TOKEN_KEYS": [_token_key()],
}

if os.environ.get("DJPA_DEMO_CODEX") == "1":
    DJ_PYDANTIC_AGENTS |= {
        "MODEL_FACTORY": CODEX_MODEL_FACTORY,
        "MODEL_NAMES": {"chat": os.environ.get("DJPA_DEMO_MODEL", "gpt-6.1-sol")},
    }
