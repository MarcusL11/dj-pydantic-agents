from pydantic_ai.messages import FunctionToolCallEvent
from pydantic_ai.messages import PartDeltaEvent
from pydantic_ai.messages import PartEndEvent
from pydantic_ai.messages import PartStartEvent
from pydantic_ai.messages import TextPart
from pydantic_ai.messages import TextPartDelta
from pydantic_ai.messages import ToolCallPart

from dj_pydantic_agents.kit.events import TURN_EVENT_ADAPTER
from dj_pydantic_agents.kit.events import ApprovalRequestedEventDTO
from dj_pydantic_agents.kit.events import PendingApprovalDTO
from dj_pydantic_agents.kit.events import TextDeltaEventDTO
from dj_pydantic_agents.kit.events import ToolCallEventDTO
from dj_pydantic_agents.kit.events import to_turn_event
from tests.testcases import SimpleTestCase


class TestToTurnEvent(SimpleTestCase):
    def test_first_text_piece_comes_from_part_start(self):
        event = PartStartEvent(index=0, part=TextPart(content="Hello"))

        assert to_turn_event(event) == TextDeltaEventDTO(text="Hello")

    def test_next_text_pieces_come_from_part_delta(self):
        event = PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=" world"))

        assert to_turn_event(event) == TextDeltaEventDTO(text=" world")

    def test_empty_text_is_skipped(self):
        event = PartStartEvent(index=0, part=TextPart(content=""))

        assert to_turn_event(event) is None

    def test_tool_call(self):
        part = ToolCallPart(tool_name="send_mail", args="{}", tool_call_id="call-1")

        assert to_turn_event(FunctionToolCallEvent(part=part)) == ToolCallEventDTO(
            tool_call_id="call-1",
            tool_name="send_mail",
        )

    def test_other_events_are_skipped(self):
        event = PartEndEvent(index=0, part=TextPart(content="Hello"))

        assert to_turn_event(event) is None


class TestTurnEventAdapter(SimpleTestCase):
    def test_json_round_trip_keeps_the_event_type(self):
        event = ApprovalRequestedEventDTO(
            approvals=(
                PendingApprovalDTO(
                    tool_call_id="c1",
                    tool_name="send_mail",
                    args_json="{}",
                ),
            ),
        )

        loaded = TURN_EVENT_ADAPTER.validate_json(TURN_EVENT_ADAPTER.dump_json(event))

        assert loaded == event
