from django.apps import AppConfig


class CodexConfig(AppConfig):
    """The ChatGPT plan login, and the models of the openai-codex provider."""

    name = "dj_pydantic_agents.contrib.codex"
    label = "dj_pydantic_agents_codex"
    verbose_name = "Pydantic agents: Codex"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # The system check registers when its module loads.
        from dj_pydantic_agents.contrib.codex import checks  # noqa: F401, PLC0415
