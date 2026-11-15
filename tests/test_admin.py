from django.contrib import admin
from django.core.management import call_command
from django.test import RequestFactory

from dj_pydantic_agents.models import Conversation
from dj_pydantic_agents.models import PendingApproval
from dj_pydantic_agents.models import Turn
from tests.testcases import SimpleTestCase


class TestAdmin(SimpleTestCase):
    def test_the_admin_passes_the_system_checks(self):
        call_command("check", "dj_pydantic_agents", fail_level="WARNING")

    def test_the_admin_pages_are_read_only(self):
        request = RequestFactory().get("/")

        for model in (Conversation, Turn, PendingApproval):
            model_admin = admin.site.get_model_admin(model)
            assert not model_admin.has_add_permission(request)
            assert not model_admin.has_change_permission(request)
            assert not model_admin.has_delete_permission(request)
