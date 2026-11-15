"""Settings of the demo project. It is for a test in a browser only.

Start it with an ASGI server, because runserver cannot stream:

    uv run django-admin migrate --settings=tests.demo.settings --pythonpath=.
    uv run --with uvicorn uvicorn tests.demo.asgi:application --port 8001
"""

import os
from pathlib import Path

from tests.settings import *  # noqa: F403

BASE_DIR = Path(__file__).parent
REDIS_TRANSPORT = "dj_pydantic_agents.transports.redis_stream.RedisStreamTransport"

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
}
