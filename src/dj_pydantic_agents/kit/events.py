"""The events of one turn, as the event transport stores them."""

from typing import Annotated
from typing import Literal

from pydantic import Field
from pydantic import TypeAdapter
from pydantic_ai.messages import AgentStreamEvent
from pydantic_ai.messages import FunctionToolCallEvent
from pydantic_ai.messages import NativeToolCallPart
from pydantic_ai.messages import PartDeltaEvent
from pydantic_ai.messages import PartEndEvent
from pydantic_ai.messages import PartStartEvent
from pydantic_ai.messages import TextPart
from pydantic_ai.messages import TextPartDelta
from pydantic_ai.messages import ToolCallPart

from dj_pydantic_agents.kit.dtos import ExternalDTO


class PendingApprovalDTO(ExternalDTO):
    tool_call_id: str
    tool_name: str
    args_json: str


class TextDeltaEventDTO(ExternalDTO):
    kind: Literal["text_delta"] = "text_delta"
    version: Literal[1] = 1
    text: str


class ToolCallEventDTO(ExternalDTO):
    """A tool call, with its arguments as JSON.

    An event from before version 0.5.1 has no arguments, so the default is "".
    """

    kind: Literal["tool_call"] = "tool_call"
    version: Literal[1] = 1
    tool_call_id: str
    tool_name: str
    args_json: str = ""


class ApprovalRequestedEventDTO(ExternalDTO):
    kind: Literal["approval_requested"] = "approval_requested"
    version: Literal[1] = 1
    approvals: tuple[PendingApprovalDTO, ...]


class TurnDoneEventDTO(ExternalDTO):
    kind: Literal["turn_done"] = "turn_done"
    version: Literal[1] = 1
    text: str


class TurnFailedEventDTO(ExternalDTO):
    kind: Literal["turn_failed"] = "turn_failed"
    version: Literal[1] = 1
    error_code: str


type TurnEventDTO = Annotated[
    TextDeltaEventDTO
    | ToolCallEventDTO
    | ApprovalRequestedEventDTO
    | TurnDoneEventDTO
    | TurnFailedEventDTO,
    Field(discriminator="kind"),
]

TURN_EVENT_ADAPTER: TypeAdapter[TurnEventDTO] = TypeAdapter(TurnEventDTO)

# A turn sends no event after one of these.
FINAL_EVENT_KINDS = frozenset({"approval_requested", "turn_done", "turn_failed"})

# The event ID before the first event of a turn.
START_EVENT_ID = "0"


class StreamedTurnEventDTO(ExternalDTO):
    """An event that a transport read, with its event ID."""

    event_id: str
    event: TurnEventDTO

    @property
    def is_final(self) -> bool:
        return self.event.kind in FINAL_EVENT_KINDS


def to_turn_event(event: AgentStreamEvent) -> TurnEventDTO | None:
    """Map one Pydantic AI stream event to a turn event, or to None to skip it.

    This is the only function that knows the Pydantic AI event types.
    """
    match event:
        case PartStartEvent(part=TextPart(content=text)) if text:
            return TextDeltaEventDTO(text=text)
        case PartDeltaEvent(delta=TextPartDelta(content_delta=text)) if text:
            return TextDeltaEventDTO(text=text)
        case FunctionToolCallEvent(part=part):
            return _tool_call(part)
        # A provider runs a native tool, such as web_search, inside its own
        # response. So no FunctionToolCallEvent comes for it. Its arguments
        # are complete only at the end of the part.
        case PartEndEvent(part=NativeToolCallPart() as part):
            return _tool_call(part)
        case _:
            return None


def _tool_call(part: ToolCallPart | NativeToolCallPart) -> ToolCallEventDTO:
    return ToolCallEventDTO(
        tool_call_id=part.tool_call_id,
        tool_name=part.tool_name,
        args_json=part.args_as_json_str(),
    )
