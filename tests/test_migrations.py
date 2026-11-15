from io import StringIO

from django.core.management import call_command

from tests.testcases import TestCase


class TestMigrations(TestCase):
    def test_the_models_have_no_missing_migration(self):
        output = StringIO()

        call_command("makemigrations", "--check", "--dry-run", stdout=output)

        assert "No changes detected" in output.getvalue()
