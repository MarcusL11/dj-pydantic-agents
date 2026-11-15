"""Named failures of the core app, without HTTP dependencies."""


class DjPydanticAgentsError(Exception):
    """The base class of the package errors."""


class ConversationNotFound(DjPydanticAgentsError):  # noqa: N818
    """The conversation does not exist, or another user owns it."""


class TurnInProgress(DjPydanticAgentsError):  # noqa: N818
    """The conversation has an active turn. Send the message after it stops."""


class ApprovalNotPending(DjPydanticAgentsError):  # noqa: N818
    """The approval does not exist, has a decision, or another user owns it."""


class TurnStateConflict(DjPydanticAgentsError):  # noqa: N818
    """The turn is not in the state that this step needs."""


class AgentNotFound(DjPydanticAgentsError):  # noqa: N818
    """No agent spec has this name."""


class AgentAccessDenied(DjPydanticAgentsError):  # noqa: N818
    """The permission extension point does not let this user use the agent."""
