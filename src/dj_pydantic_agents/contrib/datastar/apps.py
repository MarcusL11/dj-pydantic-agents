from django.apps import AppConfig


class DatastarConfig(AppConfig):
    """The send, approve and stream views, and their templates."""

    name = "dj_pydantic_agents.contrib.datastar"
    label = "dj_pydantic_agents_datastar"
    verbose_name = "Pydantic agents: Datastar"
