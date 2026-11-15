"""Minimal Django settings for the package tests."""

import os

SECRET_KEY = "dj-pydantic-agents-tests-only"  # noqa: S105

DEBUG = False
USE_TZ = True
TIME_ZONE = "UTC"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django.contrib.sessions",
    "dj_pydantic_agents",
]

# The admin system checks need these settings.
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5433"),
        "NAME": os.environ.get("POSTGRES_DB", "dj_pydantic_agents"),
        "USER": os.environ.get("POSTGRES_USER", "postgres"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "postgres"),
    },
}

DJ_PYDANTIC_AGENTS = {
    "SPECS": "tests.fakes.build_specs",
    "MODEL_FACTORY": "tests.fakes.FakeModelFactory",
    "EVENT_TRANSPORT": "tests.fakes.FakeTransport",
    "TASK_RUNNER": "tests.fakes.FakeTaskRunner",
    "REDIS_URL": os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
