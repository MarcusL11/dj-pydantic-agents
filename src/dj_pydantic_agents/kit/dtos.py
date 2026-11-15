"""Base classes for the data transfer objects of the package."""

from pydantic import BaseModel
from pydantic import ConfigDict


class InternalDTO(BaseModel):
    """Trusted contracts between views, services and repositories."""

    model_config = ConfigDict(
        frozen=True,
        strict=True,
        extra="forbid",
    )


class ExternalDTO(BaseModel):
    """Untrusted input: HTTP bodies, Datastar signals, worker and Redis payloads."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )
