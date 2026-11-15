"""Minimal Django settings for the package tests."""

import os

SECRET_KEY = "dj-pydantic-agents-tests-only"  # noqa: S105

DEBUG = False
USE_TZ = True
TIME_ZONE = "UTC"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "dj_pydantic_agents",
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

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
