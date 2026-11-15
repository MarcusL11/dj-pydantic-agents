from unittest_parametrize import param
from unittest_parametrize import parametrize

from dj_pydantic_agents.rendering.nh3_sanitizer import Nh3Sanitizer
from tests.testcases import SimpleTestCase


class TestNh3Sanitizer(SimpleTestCase):
    def to_html(self, text: str) -> str:
        return Nh3Sanitizer().to_html(text=text)

    @parametrize(
        ("text", "html"),
        [
            param("**bold** and *em*", "<p><strong>bold</strong> and <em>em</em></p>"),
            param("- one\n- two", "<ul>\n<li>one</li>\n<li>two</li>\n</ul>"),
            param("# Title", "<h1>Title</h1>"),
            param("> quote", "<blockquote>\n<p>quote</p>\n</blockquote>"),
        ],
    )
    def test_renders_markdown(self, text, html):
        assert self.to_html(text) == html

    def test_renders_a_fenced_code_block_without_its_class(self):
        html = self.to_html("```python\nx = 1 < 2\n```")

        assert html == "<pre><code>x = 1 &lt; 2\n</code></pre>"

    def test_renders_a_table(self):
        html = self.to_html("| a | b |\n|---|---|\n| 1 | 2 |")

        assert "<table>" in html
        assert "<th>a</th>" in html
        assert "<td>2</td>" in html

    def test_a_link_gets_rel(self):
        html = self.to_html('[site](https://example.com "Site")')

        assert html == (
            '<p><a href="https://example.com" title="Site" '
            'rel="noopener noreferrer">site</a></p>'
        )

    @parametrize(
        ("text", "removed"),
        [
            param("<script>alert(1)</script>", "alert", id="script"),
            param('<p onclick="alert(1)">x</p>', "onclick", id="onclick"),
            param("[x](javascript:alert(1))", "javascript", id="javascript_link"),
            param("![x](https://example.com/a.png)", "<img", id="img"),
            param('<p style="color: red">x</p>', "style", id="style"),
            param('<span class="big">x</span>', "class", id="class"),
            param("<iframe src='https://example.com'></iframe>", "iframe", id="iframe"),
        ],
    )
    def test_removes_unsafe_html(self, text, removed):
        assert removed not in self.to_html(text)
