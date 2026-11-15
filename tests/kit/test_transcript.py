from pydantic_ai.messages import ImageUrl
from pydantic_ai.messages import ModelMessage
from pydantic_ai.messages import ModelRequest
from pydantic_ai.messages import ModelResponse
from pydantic_ai.messages import SystemPromptPart
from pydantic_ai.messages import TextPart
from pydantic_ai.messages import ThinkingPart
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.messages import UserPromptPart

from dj_pydantic_agents.kit.transcript import NON_TEXT_PROMPT
from dj_pydantic_agents.kit.transcript import TranscriptLineDTO
from dj_pydantic_agents.kit.transcript import transcript_lines
from tests.testcases import SimpleTestCase


class TestTranscriptLines(SimpleTestCase):
    def test_one_line_for_each_visible_part(self):
        messages: list[ModelMessage] = [
            ModelRequest(
                parts=[
                    SystemPromptPart(content="Be brief."),
                    UserPromptPart(content="Mail Ada"),
                ],
            ),
            ModelResponse(
                parts=[
                    ThinkingPart(content="The user wants a mail."),
                    ToolCallPart(
                        tool_name="send_mail",
                        args={"to": "ada"},
                        tool_call_id="call-1",
                    ),
                ],
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="send_mail",
                        content="sent to ada",
                        tool_call_id="call-1",
                    ),
                ],
            ),
            ModelResponse(parts=[TextPart(content="I sent it.")]),
        ]

        assert transcript_lines(messages) == (
            TranscriptLineDTO(kind="user", text="Mail Ada"),
            TranscriptLineDTO(
                kind="tool_call",
                text='{"to":"ada"}',
                tool_name="send_mail",
            ),
            TranscriptLineDTO(
                kind="tool_result",
                text="sent to ada",
                tool_name="send_mail",
            ),
            TranscriptLineDTO(kind="assistant", text="I sent it."),
        )

    def test_a_prompt_with_parts_keeps_its_text(self):
        image = ImageUrl(url="https://example.com/a.png")
        messages = [
            ModelRequest(parts=[UserPromptPart(content=["Look", image])]),
            ModelRequest(parts=[UserPromptPart(content=[image])]),
        ]

        assert transcript_lines(messages) == (
            TranscriptLineDTO(kind="user", text="Look"),
            TranscriptLineDTO(kind="user", text=NON_TEXT_PROMPT),
        )
