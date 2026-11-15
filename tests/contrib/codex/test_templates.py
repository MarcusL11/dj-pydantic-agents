from django.template.loader import render_to_string

from tests.testcases import SimpleTestCase


class TestLoginFormTemplate(SimpleTestCase):
    def test_shows_the_link_the_error_and_the_paste_form(self):
        html = render_to_string(
            "dj_pydantic_agents/codex/login_form.html",
            {
                "authorization_url": "https://auth.openai.com/oauth/authorize?state=s",
                "form_action": "/plan/complete/",
                "error": "Start the login again.",
            },
        )

        assert 'href="https://auth.openai.com/oauth/authorize?state=s"' in html
        assert 'action="/plan/complete/"' in html
        assert 'name="pasted_url"' in html
        assert "Start the login again." in html
