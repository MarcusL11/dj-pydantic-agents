from django.apps import AppConfig


class DjPydanticAgentsConfig(AppConfig):
    name = "dj_pydantic_agents"
    label = "dj_pydantic_agents"
    verbose_name = "Pydantic agents"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # The system checks register when their module loads. Nothing else
        # goes here: the package wires its services in composition.py.
        from dj_pydantic_agents import checks  # noqa: F401, PLC0415
