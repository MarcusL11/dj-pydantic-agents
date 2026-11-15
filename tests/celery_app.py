"""The Celery app of the tests. A test module that sends a task imports it."""

from celery import Celery

app = Celery("tests")
app.config_from_object("django.conf:settings", namespace="CELERY")
