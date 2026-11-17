"""Include these URLs in the project URLs. The namespace is dj_pydantic_agents."""

from django.urls import path

from dj_pydantic_agents.contrib.datastar import views

app_name = "dj_pydantic_agents"

urlpatterns = [
    path(
        "conversations/<str:conversation_id>/messages/",
        views.send_message,
        name="send_message",
    ),
    path(
        "approvals/<str:approval_id>/decision/",
        views.decide_approval,
        name="decide_approval",
    ),
    path("turns/<str:turn_id>/stream/", views.stream_turn, name="stream_turn"),
    path(
        "conversations/<str:conversation_id>/attachments/",
        views.upload_attachments,
        name="upload_attachments",
    ),
    path(
        "attachments/<str:attachment_id>/remove/",
        views.remove_attachment,
        name="remove_attachment",
    ),
    path(
        "attachments/<str:attachment_id>/",
        views.attachment_file,
        name="attachment_file",
    ),
]
