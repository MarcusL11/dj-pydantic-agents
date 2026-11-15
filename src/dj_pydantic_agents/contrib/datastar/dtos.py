"""The form fields that the send and approve views read."""

from typing import Annotated

from pydantic import StringConstraints

from dj_pydantic_agents.kit.dtos import ExternalDTO


class SendMessagePayloadDTO(ExternalDTO):
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ApprovalDecisionPayloadDTO(ExternalDTO):
    approved: bool
