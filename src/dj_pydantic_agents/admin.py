"""Read-only admin pages, to examine conversations, turns and approvals."""

from typing import TYPE_CHECKING

from django.contrib import admin

from dj_pydantic_agents.models import Conversation
from dj_pydantic_agents.models import PendingApproval
from dj_pydantic_agents.models import Turn

if TYPE_CHECKING:
    from django.db.models import Model
    from django.http import HttpRequest


class ReadOnlyAdmin(admin.ModelAdmin):
    """Only the package services change these rows."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: Model | None = None,
    ) -> bool:
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: Model | None = None,
    ) -> bool:
        return False


@admin.register(Conversation)
class ConversationAdmin(ReadOnlyAdmin):
    list_display = ["id", "title", "agent_name", "owner", "updated_at"]
    list_filter = ["agent_name"]
    list_select_related = ["owner"]
    search_fields = ["id", "title"]
    date_hierarchy = "created_at"


@admin.register(Turn)
class TurnAdmin(ReadOnlyAdmin):
    list_display = [
        "id",
        "conversation",
        "requested_by",
        "status",
        "requests",
        "input_tokens",
        "output_tokens",
        "error_code",
        "created_at",
    ]
    list_filter = ["status", "error_code"]
    list_select_related = ["conversation", "requested_by"]
    search_fields = ["id", "conversation__id"]
    date_hierarchy = "created_at"


@admin.register(PendingApproval)
class PendingApprovalAdmin(ReadOnlyAdmin):
    list_display = ["id", "turn", "tool_name", "decision", "decided_by", "decided_at"]
    list_filter = ["decision", "tool_name"]
    list_select_related = ["turn", "decided_by"]
    search_fields = ["id", "turn__id", "tool_call_id"]
