"""Named failures of the core app, without HTTP dependencies."""

from typing import ClassVar


class DjPydanticAgentsError(Exception):
    """The base class of the package errors.

    A turn that fails with an error that has an error_code records that code.
    """

    error_code: ClassVar[str | None] = None


class ConversationNotFound(DjPydanticAgentsError):  # noqa: N818
    """The conversation does not exist, or another user owns it."""


class TurnInProgress(DjPydanticAgentsError):  # noqa: N818
    """The conversation has an active turn. Send the message after it stops."""


class ApprovalNotPending(DjPydanticAgentsError):  # noqa: N818
    """The approval does not exist, has a decision, or another user owns it."""


class TurnNotQueued(DjPydanticAgentsError):  # noqa: N818
    """The task runner did not take the turn, so the turn failed with error_code."""

    error_code = "enqueue_failed"

    def __init__(self, message: str, *, turn_id: str, conversation_id: str) -> None:
        super().__init__(message)
        self.turn_id = turn_id
        self.conversation_id = conversation_id


class TurnStateConflict(DjPydanticAgentsError):  # noqa: N818
    """The turn is not in the state that this step needs."""


class AgentNotFound(DjPydanticAgentsError):  # noqa: N818
    """No agent spec has this name."""

    error_code = "agent_not_found"


class AgentAccessDenied(DjPydanticAgentsError):  # noqa: N818
    """The permission extension point does not let this user use the agent."""


class FilesRefused(DjPydanticAgentsError):  # noqa: N818
    """PROMPT_FILES did not take the files of a message. The text tells the user why."""
