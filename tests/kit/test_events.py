from pydantic_ai.messages import FunctionToolCallEvent
from pydantic_ai.messages import NativeToolCallPart
from pydantic_ai.messages import PartDeltaEvent
from pydantic_ai.messages import PartEndEvent
from pydantic_ai.messages import PartStartEvent
from pydantic_ai.messages import TextPart
from pydantic_ai.messages import TextPartDelta
from pydantic_ai.messages import ToolCallPart
from unittest_parametrize import param
from unittest_parametrize import parametrize

from dj_pydantic_agents.kit.events import TURN_EVENT_ADAPTER
from dj_pydantic_agents.kit.events import ApprovalRequestedEventDTO
from dj_pydantic_agents.kit.events import PendingApprovalDTO
from dj_pydantic_agents.kit.events import StreamedTurnEventDTO
from dj_pydantic_agents.kit.events import TextDeltaEventDTO
from dj_pydantic_agents.kit.events import ToolCallEventDTO
from dj_pydantic_agents.kit.events import TurnDoneEventDTO
from dj_pydantic_agents.kit.events import TurnFailedEventDTO
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
            args_json="{}",
        )

    def test_native_tool_call_comes_at_the_end_with_its_arguments(self):
        part = NativeToolCallPart(
            tool_name="web_search",
            args={"query": "Rolex 1675"},
            tool_call_id="ws-1",
        )

        assert to_turn_event(PartEndEvent(index=0, part=part)) == ToolCallEventDTO(
            tool_call_id="ws-1",
            tool_name="web_search",
            args_json='{"query":"Rolex 1675"}',
        )

    def test_the_start_of_a_native_tool_call_is_skipped(self):
        """The arguments of a native call are empty at its start."""
        part = NativeToolCallPart(tool_name="web_search", tool_call_id="ws-1")

        assert to_turn_event(PartStartEvent(index=0, part=part)) is None

    def test_an_old_tool_call_event_has_no_arguments(self):
        data = '{"kind":"tool_call","version":1,"tool_call_id":"c1","tool_name":"x"}'

        event = TURN_EVENT_ADAPTER.validate_json(data)

        assert event == ToolCallEventDTO(tool_call_id="c1", tool_name="x")
        assert event.args_json == ""

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


class TestStreamedTurnEvent(SimpleTestCase):
    @parametrize(
        ("event", "is_final"),
        [
            param(TextDeltaEventDTO(text="Hi"), False, id="text_delta"),
            param(
                ToolCallEventDTO(tool_call_id="c1", tool_name="send_mail"),
                False,
                id="tool_call",
            ),
            param(ApprovalRequestedEventDTO(approvals=()), True, id="approval"),
            param(TurnDoneEventDTO(text="Hi"), True, id="done"),
            param(TurnFailedEventDTO(error_code="model_error"), True, id="failed"),
        ],
    )
    def test_marks_the_final_events(self, event, is_final):
        streamed = StreamedTurnEventDTO(event_id="1-0", event=event)

        assert streamed.is_final is is_final
