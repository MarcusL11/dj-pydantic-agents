from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.test import override_settings
from django.urls import reverse
from unittest_parametrize import param
from unittest_parametrize import parametrize

from dj_pydantic_agents.contrib.datastar.rendering import render_message_form
from dj_pydantic_agents.contrib.datastar.rendering import render_transcript_line
from dj_pydantic_agents.dtos.conversation_queries import ActiveTurnProjectionDTO
from dj_pydantic_agents.dtos.conversation_queries import ApprovalProjectionDTO
from dj_pydantic_agents.kit.attachments import PromptFileRefDTO
from dj_pydantic_agents.kit.transcript import TranscriptLineDTO
from tests.builders import APPROVAL_ID
from tests.builders import CONVERSATION_ID
from tests.builders import TURN_ID
from tests.builders import a_page
from tests.builders import an_attachment
from tests.contrib.datastar.forms import form_is_closed
from tests.testcases import SimpleTestCase

PROJECT_TEMPLATES = Path(__file__).parent / "templates"
# A project with a CSRF bridge: its csrf_option.html is empty.
BRIDGE_TEMPLATES = Path(__file__).parent / "bridge_templates"
CSRF_TOKEN = "csrf-token-value"  # noqa: S105


def render_chat(**page_values) -> str:
    return render_to_string(
        "dj_pydantic_agents/chat.html",
        {"page": a_page(**page_values), "csrf_token": CSRF_TOKEN},
    )


class TestChatAttachments(SimpleTestCase):
    def test_the_form_shows_the_pending_files_and_the_file_input(self):
        html = render_chat(pending_attachments=(an_attachment(),))

        attachment = an_attachment()
        assert f'name="attachment" value="{attachment.attachment_id}"' in html
        assert "invoice.pdf" in html
        remove_url = reverse(
            "dj_pydantic_agents:remove_attachment",
            args=[attachment.attachment_id],
        )
        assert f"@post('{remove_url}'" in html
        assert 'type="file"' in html
        assert 'form="djpa-upload-form"' in html
        assert 'accept="image/png,' in html
        upload_url = reverse(
            "dj_pydantic_agents:upload_attachments",
            args=[CONVERSATION_ID],
        )
        assert 'id="djpa-upload-form" enctype="multipart/form-data"' in html
        assert f"data-on:djpa-upload=\"@post('{upload_url}'" in html

    def test_a_chat_with_no_types_has_no_file_input(self):
        values = {**settings.DJ_PYDANTIC_AGENTS, "ATTACHMENT_TYPES": ()}

        with override_settings(DJ_PYDANTIC_AGENTS=values):
            html = render_chat()

        assert 'type="file"' not in html

    def test_a_user_line_shows_its_files_before_the_text(self):
        html = render_transcript_line(
            kind="user",
            text="Read",
            files=(
                PromptFileRefDTO(
                    attachment_id="att_1",
                    name="code.pdf",
                    media_type="application/pdf",
                    is_image=False,
                    size=1403,
                ),
                PromptFileRefDTO(
                    attachment_id="att_2",
                    name="dial.png",
                    media_type="image/png",
                    is_image=True,
                ),
            ),
        )

        image_url = reverse("dj_pydantic_agents:attachment_file", args=["att_2"])
        document_url = reverse("dj_pydantic_agents:attachment_file", args=["att_1"])
        assert (
            f'<a class="djpa-file djpa-file--image" href="{image_url}" '
            'target="_blank" rel="noopener" title="dial.png">'
            f'<img src="{image_url}" alt="dial.png" loading="lazy"></a>'
        ) in html
        assert (
            f'<a class="djpa-file djpa-file--document" href="{document_url}" '
            'target="_blank" rel="noopener" title="code.pdf">'
        ) in html
        assert '<span class="djpa-file__badge">PDF</span>' in html
        assert '<span class="djpa-file__size">1.4\xa0KB</span>' in html
        # The images come first, then the documents, then the text of the user.
        assert (
            html.index("djpa-files__images")
            < html.index("djpa-files__documents")
            < html.index("djpa-line--user")
        )

    def test_a_file_with_no_size_shows_no_size(self):
        html = render_transcript_line(
            kind="user",
            text="Read",
            files=(
                PromptFileRefDTO(
                    attachment_id="att_1",
                    name="code.pdf",
                    media_type="application/pdf",
                    is_image=False,
                ),
            ),
        )

        assert "djpa-file__size" not in html
        assert "djpa-files__images" not in html

    def test_an_unsaved_prompt_shows_its_files(self):
        html = render_chat(
            active_turn=ActiveTurnProjectionDTO(
                turn_id=TURN_ID,
                status="running",
                unsaved_prompt="Read",
                unsaved_files=(an_attachment(),),
            ),
        )

        assert "djpa-file--document" in html


class TestChatTemplate(SimpleTestCase):
    def test_shows_the_lines_and_an_open_form(self):
        html = render_chat(
            lines=(
                TranscriptLineDTO(kind="user", text="Hi"),
                TranscriptLineDTO(kind="assistant", text="Hello **Ada**"),
            ),
        )

        assert 'data-signals="{_djpaStream: 0, _djpaUploading: false}"' in html
        assert '<div class="djpa-chat__scroll">' in html
        assert "djpa-line--user" in html
        assert "<strong>Ada</strong>" in html
        assert "djpa-reply" not in html
        send_url = reverse("dj_pydantic_agents:send_message", args=[CONVERSATION_ID])
        assert f"@post('{send_url}'" in html
        assert f"headers: {{'X-CSRFToken': '{CSRF_TOKEN}'}}" in html
        assert not form_is_closed(html)

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
        assert form_is_closed(html)

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


class TestToolLabel(SimpleTestCase):
    @parametrize(
        ("state", "label"),
        [
            param("running", "Delegating a task", id="running"),
            param("called", "Delegated a task", id="called"),
            param("result", "Result of a task", id="result"),
        ],
    )
    def test_a_delegated_task_has_its_own_words(self, state, label):
        html = render_to_string(
            "dj_pydantic_agents/tool_label.html",
            {"tool_name": "delegate_task", "state": state},
        )

        assert html == label


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

        assert (
            f"{{contentType: 'form', headers: {{'X-CSRFToken': '{CSRF_TOKEN}'}}}})"
            in html
        )

    def test_an_empty_csrf_option_leaves_valid_options(self):
        with override_settings(
            TEMPLATES=[
                {
                    "BACKEND": "django.template.backends.django.DjangoTemplates",
                    "DIRS": [BRIDGE_TEMPLATES],
                    "APP_DIRS": True,
                },
            ],
        ):
            html = render_chat(pending_attachments=(an_attachment(),))

        assert "X-CSRFToken" not in html
        assert "{contentType: 'form', })" in html
        assert "{filterSignals: {include: /^$/}, })" in html
