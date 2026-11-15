from django.urls import include
from django.urls import path

from tests.demo import views

demo_patterns = (
    [
        path("", views.conversation_list, name="list"),
        path("new/", views.new_conversation, name="new"),
        path("chat/<str:conversation_id>/", views.chat, name="chat"),
    ],
    "demo",
)

urlpatterns = [
    path("", include(demo_patterns)),
    path("agents/", include("dj_pydantic_agents.contrib.datastar.urls")),
]
