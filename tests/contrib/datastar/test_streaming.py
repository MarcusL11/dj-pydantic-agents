from unittest_parametrize import param
from unittest_parametrize import parametrize

from dj_pydantic_agents.contrib.datastar.streaming import TextReveal
from dj_pydantic_agents.contrib.datastar.streaming import close_open_markdown
from dj_pydantic_agents.contrib.datastar.streaming import number_blocks
from tests.testcases import SimpleTestCase


class TestTextReveal(SimpleTestCase):
    def test_a_step_shows_a_part_of_the_waiting_text_to_the_end_of_a_word(self):
        text = TextReveal()
        text.add("one two three four five six seven eight")

        text.step()

        assert text.shown == "one two three "
        assert text.is_waiting

    def test_the_steps_show_the_full_text(self):
        text = TextReveal()
        text.add("one two three four five six seven eight")
        steps = []

        while text.is_waiting:
            text.step()
            steps.append(text.shown)

        assert steps == [
            "one two three ",
            "one two three four five ",
            "one two three four five six ",
            "one two three four five six seven ",
            "one two three four five six seven eight",
        ]

    def test_a_step_shows_a_part_of_a_word_when_no_space_comes(self):
        text = TextReveal()
        text.add("Hel")

        text.step()

        assert text.shown == "Hel"
        assert not text.is_waiting

    def test_show_all_and_clear(self):
        text = TextReveal()
        text.add("one two")

        text.show_all()
        assert (text.shown, text.is_waiting) == ("one two", False)

        text.clear()
        assert text.shown == ""


class TestCloseOpenMarkdown(SimpleTestCase):
    @parametrize(
        ("text", "closed"),
        [
            param("Hello **Ada", "Hello **Ada**", id="bold"),
            param("Run `ls -l", "Run `ls -l`", id="inline_code"),
            param("A ``` b", "A ``` b`", id="odd_backticks"),
            param("```python\nx = 1", "```python\nx = 1\n```", id="fence"),
            param("~~~~\nx\n~~~", "~~~~\nx\n~~~\n~~~~", id="short_closing_fence"),
            param("Text\n\n| a | b |", "Text", id="table_header_only"),
            param(
                "| a | b |\n|---|---|\n| 1",
                "| a | b |\n|---|---|\n| 1",
                id="table_with_delimiter",
            ),
            param("`**`", "`**`", id="bold_mark_in_code"),
            param("**Done** ", "**Done**", id="closed_text"),
            param(
                "```\nx\n```\n\nNow **b",
                "```\nx\n```\n\nNow **b**",
                id="after_fence",
            ),
        ],
    )
    def test_closes_the_open_markdown(self, text: str, closed: str):
        assert close_open_markdown(text) == closed


class TestNumberBlocks(SimpleTestCase):
    def test_gives_each_top_level_element_an_id(self):
        html = (
            "<p>Hi <strong>a</strong> &amp; b</p>\n"
            "<ul>\n<li>one</li>\n</ul>\n<hr>\n"
            '<p><a href="https://x.test/?a=1&amp;b=2" title="a>b">x</a><br>y</p>'
        )

        blocks = number_blocks(html, id_prefix="t-")

        assert blocks == (
            '<p id="t-0">Hi <strong>a</strong> &amp; b</p>',
            '<ul id="t-1">\n<li>one</li>\n</ul>',
            '<hr id="t-2">',
            '<p id="t-3"><a href="https://x.test/?a=1&amp;b=2" title="a>b">x</a>'
            "<br>y</p>",
        )

    def test_an_empty_text_has_no_blocks(self):
        assert number_blocks("", id_prefix="t-") == ()

    @parametrize(
        ("html",),
        [
            param("loose <p>x</p>", id="text"),
            param("&amp;<p>x</p>", id="entity"),
        ],
    )
    def test_text_outside_an_element_has_no_blocks(self, html: str):
        assert number_blocks(html, id_prefix="t-") is None
