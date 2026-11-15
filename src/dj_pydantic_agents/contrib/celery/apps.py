from django.apps import AppConfig


class CeleryConfig(AppConfig):
    """Add this app so that app.autodiscover_tasks() finds the turn task."""

    name = "dj_pydantic_agents.contrib.celery"
    label = "dj_pydantic_agents_celery"
    verbose_name = "Pydantic agents: Celery"
