"""The form fields that the send and approve views read."""

from typing import Annotated

from pydantic import Field
from pydantic import StringConstraints

from dj_pydantic_agents.kit.dtos import ExternalDTO


class SendMessagePayloadDTO(ExternalDTO):
    """A message needs text. file_ids are the IDs of its pending files."""

    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    file_ids: tuple[str, ...] = Field(default=(), max_length=100)


class ApprovalDecisionPayloadDTO(ExternalDTO):
    approved: bool
