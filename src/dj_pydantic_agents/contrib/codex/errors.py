"""Named failures of the ChatGPT plan login and of the plan tokens."""

from dj_pydantic_agents.errors import DjPydanticAgentsError


class PlanNotConnected(DjPydanticAgentsError):  # noqa: N818
    """The user has no usable plan tokens. The user must log in again."""

    error_code = "plan_not_connected"


class PlanLoginFailed(DjPydanticAgentsError):  # noqa: N818
    """The pasted address does not complete a login. The user must start again."""
