"""Error codes for a failed turn."""

from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.exceptions import ModelQuotaExceededError
from pydantic_ai.exceptions import ModelRateLimitError
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.providers.openai_codex import CredentialsRefreshError

INTERNAL_ERROR = "internal_error"

# The order is important: a subclass comes before its base class.
_ERROR_CODES: tuple[tuple[type[BaseException], str], ...] = (
    (UsageLimitExceeded, "usage_limit"),
    (CredentialsRefreshError, "credentials"),
    (ModelRateLimitError, "rate_limited"),
    (ModelQuotaExceededError, "quota_exceeded"),
    (ModelAPIError, "model_api_error"),
    (UnexpectedModelBehavior, "model_behavior"),
)


def error_code_for(error: BaseException) -> str:
    return next(
        (code for error_type, code in _ERROR_CODES if isinstance(error, error_type)),
        INTERNAL_ERROR,
    )
