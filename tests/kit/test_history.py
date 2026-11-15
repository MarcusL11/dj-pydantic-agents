from pydantic_ai.messages import ModelMessage
from pydantic_ai.messages import ModelRequest
from pydantic_ai.messages import ModelResponse
from pydantic_ai.messages import TextPart
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.messages import UserPromptPart
from pydantic_ai.tools import DeferredToolRequests

from dj_pydantic_agents.kit.events import PendingApprovalDTO
from dj_pydantic_agents.kit.history import describe_pending
from dj_pydantic_agents.kit.history import messages_from_json
from dj_pydantic_agents.kit.history import messages_to_json
from dj_pydantic_agents.kit.history import pending_from_json
from dj_pydantic_agents.kit.history import pending_to_json
from tests.testcases import SimpleTestCase

SEND_MAIL_CALL = ToolCallPart(
    tool_name="send_mail",
    args={"to": "ada"},
    tool_call_id="call-1",
)


class TestMessagesJson(SimpleTestCase):
    def test_round_trip(self):
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hi")]),
            ModelResponse(parts=[TextPart(content="Hello")]),
        ]

        assert messages_from_json(messages_to_json(messages)) == messages


class TestPendingJson(SimpleTestCase):
    def test_round_trip(self):
        pending = DeferredToolRequests(approvals=[SEND_MAIL_CALL])

        assert pending_from_json(pending_to_json(pending)) == pending

    def test_none_stays_none(self):
        assert pending_to_json(None) is None
        assert pending_from_json(None) is None


class TestDescribePending(SimpleTestCase):
    def test_lists_each_approval_with_json_args(self):
        pending = DeferredToolRequests(approvals=[SEND_MAIL_CALL])

        assert describe_pending(pending) == (
            PendingApprovalDTO(
                tool_call_id="call-1",
                tool_name="send_mail",
                args_json='{"to":"ada"}',
            ),
        )
