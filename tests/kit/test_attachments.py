from pydantic_ai.messages import BinaryContent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.messages import ModelRequest
from pydantic_ai.messages import ModelResponse
from pydantic_ai.messages import TextPart
from pydantic_ai.messages import UserPromptPart

from dj_pydantic_agents.kit.attachments import EARLIER_NOTE
from dj_pydantic_agents.kit.attachments import FileRefDTO
from dj_pydantic_agents.kit.attachments import PromptFile
from dj_pydantic_agents.kit.attachments import split_prompt
from dj_pydantic_agents.kit.attachments import user_prompt
from dj_pydantic_agents.kit.attachments import with_file_data
from dj_pydantic_agents.kit.attachments import without_file_data
from dj_pydantic_agents.kit.history import messages_from_json
from dj_pydantic_agents.kit.history import messages_to_json
from dj_pydantic_agents.kit.transcript import TranscriptLineDTO
from dj_pydantic_agents.kit.transcript import transcript_lines
from tests.testcases import SimpleTestCase

PDF = PromptFile(
    file_id="fil_1",
    turn_id="trn_1",
    name="invoice.pdf",
    media_type="application/pdf",
    data=b"%PDF-1.7",
)
PNG = PromptFile(
    file_id="fil_2",
    turn_id="trn_1",
    name="dial.png",
    media_type="image/png",
    data=b"\x89PNG",
)
PDF_REF = FileRefDTO(
    file_id="fil_1",
    name="invoice.pdf",
    media_type="application/pdf",
)
PNG_REF = FileRefDTO(
    file_id="fil_2",
    name="dial.png",
    media_type="image/png",
)


def conversation(*files: PromptFile) -> list[ModelMessage]:
    return [
        ModelRequest(
            parts=[UserPromptPart(content=user_prompt(text="Read", files=files))],
        ),
        ModelResponse(parts=[TextPart(content="Done.")]),
    ]


def first_prompt(messages: list[ModelMessage]) -> object:
    request = messages[0]
    assert isinstance(request, ModelRequest)
    part = request.parts[0]
    assert isinstance(part, UserPromptPart)
    return part.content


class TestUserPrompt(SimpleTestCase):
    def test_no_files_give_the_text(self):
        assert user_prompt(text="Hi", files=()) == "Hi"

    def test_each_file_gets_a_label_and_its_bytes(self):
        content = user_prompt(text="Read", files=(PDF, PNG))

        assert content[:2] == ["Read", "Attached file: invoice.pdf"]
        assert content[3] == "Attached file: dial.png"
        assert isinstance(content[2], BinaryContent)
        assert (content[2].identifier, content[2].data) == ("fil_1", b"%PDF-1.7")
        assert isinstance(content[4], BinaryContent)
        assert content[4].is_image


class TestFileData(SimpleTestCase):
    def test_the_stored_history_has_no_bytes_and_keeps_the_identifier(self):
        stored = messages_to_json(
            without_file_data(conversation(PDF), file_ids={"fil_1"}),
        )

        assert stored[0]["parts"][0]["content"][2]["data"] == ""
        assert stored[0]["parts"][0]["content"][2]["identifier"] == "fil_1"

    def test_the_bytes_go_back_in(self):
        stored = messages_from_json(
            messages_to_json(
                without_file_data(conversation(PDF), file_ids={"fil_1"}),
            ),
        )

        filled = with_file_data(stored, files=(PDF,))

        content = first_prompt(filled)
        assert isinstance(content, list)
        assert content[2].data == b"%PDF-1.7"
        assert content[2].identifier == "fil_1"

    def test_a_file_with_no_bytes_goes_and_its_label_tells_the_model(self):
        stored = without_file_data(
            conversation(PDF, PNG),
            file_ids={"fil_1", "fil_2"},
        )

        filled = with_file_data(stored, files=(PNG,))

        content = first_prompt(filled)
        assert isinstance(content, list)
        assert content[:2] == ["Read", f"Attached file: invoice.pdf{EARLIER_NOTE}"]
        assert content[2] == "Attached file: dial.png"
        assert isinstance(content[3], BinaryContent)
        assert len(content) == 4  # noqa: PLR2004

    def test_other_bytes_and_text_prompts_do_not_change(self):
        messages = conversation(PDF)

        assert without_file_data(messages, file_ids={"fil_9"}) == messages
        assert with_file_data(messages, files=()) == messages


class TestSplitPrompt(SimpleTestCase):
    def test_gives_the_text_and_the_files(self):
        content = user_prompt(text="Read", files=(PDF, PNG))

        assert split_prompt(content) == ("Read", (PDF_REF, PNG_REF))

    def test_a_label_text_with_no_file_is_text_of_the_user(self):
        assert split_prompt(["Attached file: x"]) == ("Attached file: x", ())


class TestTranscriptFiles(SimpleTestCase):
    def test_a_user_line_shows_the_files_of_its_prompt(self):
        stored = without_file_data(conversation(PDF), file_ids={"fil_1"})

        assert transcript_lines(stored)[0] == TranscriptLineDTO(
            kind="user",
            text="Read",
            files=(PDF_REF,),
        )
