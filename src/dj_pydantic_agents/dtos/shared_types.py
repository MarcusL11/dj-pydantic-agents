"""Types that many DTO modules share."""

from typing import Any
from uuid import UUID

# The primary key of AUTH_USER_MODEL. Each project selects its own type. The
# django-stubs types see only the int key of the test User model, so the
# repositories ignore the type error of each user lookup.
type UserId = int | str | UUID

type MessageJson = dict[str, Any]
