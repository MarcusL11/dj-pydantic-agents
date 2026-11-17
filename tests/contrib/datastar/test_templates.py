from pathlib import Path

from django.template.loader import render_to_string
from django.test import override_settings
from django.urls import reverse

from dj_pydantic_agents.contrib.datastar.rendering import render_message_form
from dj_pydantic_agents.contrib.datastar.rendering import render_transcript_line
from dj_pydantic_agents.dtos.conversation_queries import ActiveTurnProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import ApprovalProjectionDTO
from dj_pydantic_agents.kit.transcript import TranscriptLineDTO
from tests.builders import APPROVAL_ID
from tests.builders import CONVERSATION_ID
from tests.builders import TURN_ID
from tests.builders import a_page
from tests.testcases import SimpleTestCase

PROJECT_TEMPLATES = Path(__file__).parent / "templates"
CSRF_TOKEN = "csrf-token-value"  # noqa: S105


def render_chat(**page_values) -> str:
    return render_to_string(
        "dj_pydantic_agents/chat.html",
        {"page": a_page(**page_values), "csrf_token": CSRF_TOKEN},
    )


class TestChatTemplate(SimpleTestCase):
    def test_shows_the_lines_and_an_open_form(self):
        html = render_chat(
            lines=(
                TranscriptLineDTO(kind="user", text="Hi"),
                TranscriptLineDTO(kind="assistant", text="Hello **Ada**"),
            ),
        )

        assert 'data-signals="{_djpaStream: 0}"' in html
        assert '<div class="djpa-chat__scroll">' in html
        assert "djpa-line--user" in html
        assert "<strong>Ada</strong>" in html
        assert "djpa-reply" not in html
        send_url = reverse("dj_pydantic_agents:send_message", args=[CONVERSATION_ID])
        assert f"@post('{send_url}'" in html
        assert f"headers: {{'X-CSRFToken': '{CSRF_TOKEN}'}}" in html
        assert "disabled" not in html

    def test_a_running_turn_shows_its_prompt_and_a_streaming_reply(self):
        html = render_chat(
            active_turn=ActiveTurnProjectionDTO(
                turn_id=TURN_ID,
                status="running",
                unsaved_prompt="How are you?",
            ),
        )

        assert "How are you?" in html
        assert f'id="djpa-reply-{TURN_ID}"' in html
        assert f'id="djpa-reply-{TURN_ID}-steps"' in html
        assert "requestCancellation: 'cleanup'" in html
        assert "disabled" in html

    def test_a_waiting_turn_shows_the_approval_cards(self):
        html = render_chat(
            active_turn=ActiveTurnProjectionDTO(
                turn_id=TURN_ID,
                status="waiting_approval",
                unsaved_prompt=None,
            ),
            approvals=(
                ApprovalProjectionDTO(
                    approval_id=APPROVAL_ID,
                    tool_name="send_mail",
                    args_json='{"to":"ada"}',
                ),
            ),
        )

        decide_url = reverse("dj_pydantic_agents:decide_approval", args=[APPROVAL_ID])
        assert f"@post('{decide_url}'" in html
        assert 'name="approved" value="true"' in html
        assert 'name="approved" value="false"' in html
        assert f"'X-CSRFToken': '{CSRF_TOKEN}'" in html
        assert "djpa-reply" not in html


def render_tool_line(*, kind: str, text: str, tool_name: str) -> str:
    return render_to_string(
        "dj_pydantic_agents/transcript_line.html",
        {"kind": kind, "text": text, "tool_name": tool_name},
    ).strip()


class TestToolLines(SimpleTestCase):
    def test_a_web_search_call_is_a_closed_block_with_its_data(self):
        html = render_tool_line(
            kind="tool_call",
            text='{"query":"Rolex"}',
            tool_name="web_search",
        )

        assert html.startswith('<details class="djpa-line djpa-line--tool-call">')
        assert " open" not in html
        assert "Searched the web</summary>" in html
        assert "{&quot;query&quot;:&quot;Rolex&quot;}" in html

    def test_another_tool_call_and_its_result_name_the_tool(self):
        call = render_tool_line(
            kind="tool_call",
            text="{}",
            tool_name="send_mail",
        )
        result = render_tool_line(
            kind="tool_result",
            text="sent",
            tool_name="send_mail",
        )

        assert "Used send_mail</summary>" in call
        assert result.startswith('<details class="djpa-line djpa-line--tool-result">')
        assert "Result of send_mail</summary>" in result


class TestTemplateOverride(SimpleTestCase):
    def test_a_project_template_at_the_same_path_wins(self):
        with override_settings(
            TEMPLATES=[
                {
                    "BACKEND": "django.template.backends.django.DjangoTemplates",
                    "DIRS": [PROJECT_TEMPLATES],
                    "APP_DIRS": True,
                },
            ],
        ):
            html = render_transcript_line(kind="user", text="Hi")

        assert html.strip() == '<p class="project-line">user: Hi</p>'

    def test_the_form_sends_the_csrf_token_in_a_header(self):
        html = render_message_form(
            conversation_id=CONVERSATION_ID,
            is_closed=False,
            csrf_token=CSRF_TOKEN,
        )

        assert "contentType: 'form'" in html
        assert f"headers: {{'X-CSRFToken': '{CSRF_TOKEN}'}}" in html
