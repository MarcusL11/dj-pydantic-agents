from unittest_parametrize import param
from unittest_parametrize import parametrize

from dj_pydantic_agents.permissions import StaffPermission
from tests.factories import UserFactory
from tests.testcases import TestCase


class TestStaffPermission(TestCase):
    @parametrize(
        ("is_staff", "is_active", "allowed"),
        [
            param(True, True, True, id="active_staff"),
            param(False, True, False, id="not_staff"),
            param(True, False, False, id="inactive_staff"),
        ],
    )
    def test_allows_active_staff_only(self, is_staff, is_active, allowed):
        user = UserFactory.create(is_staff=is_staff, is_active=is_active)

        assert StaffPermission().can_use(user_id=user.pk, agent_name="any") is allowed

    def test_an_unknown_user_is_not_allowed(self):
        assert StaffPermission().can_use(user_id=0, agent_name="any") is False
