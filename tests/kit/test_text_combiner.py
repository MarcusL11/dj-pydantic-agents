from dj_pydantic_agents.kit.events import TextDeltaEventDTO
from dj_pydantic_agents.kit.events import ToolCallEventDTO
from dj_pydantic_agents.kit.events import TurnEventDTO
from dj_pydantic_agents.kit.text_combiner import TEXT_INTERVAL_SECONDS
from dj_pydantic_agents.kit.text_combiner import TextCombiner
from tests.testcases import SimpleTestCase

TOOL_CALL = ToolCallEventDTO(tool_call_id="call-1", tool_name="send_mail")


class TestTextCombiner(SimpleTestCase):
    def setUp(self):
        self.now = 100.0
        self.published: list[TurnEventDTO] = []
        self.combiner = TextCombiner(self.published.append, clock=lambda: self.now)

    def text(self, text: str, *, after: float = 0.0) -> None:
        self.now += after
        self.combiner(TextDeltaEventDTO(text=text))

    def texts(self) -> list[str]:
        return [
            event.text
            for event in self.published
            if isinstance(event, TextDeltaEventDTO)
        ]

    def test_publishes_the_first_text_at_once(self):
        self.text("Hello")

        assert self.texts() == ["Hello"]

    def test_combines_the_texts_inside_the_interval(self):
        self.text("Hello")
        self.text(" there", after=0.01)
        self.text(" again", after=0.01)
        self.text("!", after=TEXT_INTERVAL_SECONDS)

        assert self.texts() == ["Hello", " there again!"]

    def test_publishes_the_waiting_text_before_another_event(self):
        self.text("Hello")
        self.text(" there", after=0.01)
        self.combiner(TOOL_CALL)

        assert self.published == [
            TextDeltaEventDTO(text="Hello"),
            TextDeltaEventDTO(text=" there"),
            TOOL_CALL,
        ]

    def test_flush_publishes_the_last_text(self):
        self.text("Hello")
        self.text(" there", after=0.01)

        self.combiner.flush()
        self.combiner.flush()

        assert self.texts() == ["Hello", " there"]
