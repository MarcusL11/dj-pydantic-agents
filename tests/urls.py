from django.urls import include
from django.urls import path

urlpatterns = [
    path("agents/", include("dj_pydantic_agents.contrib.datastar.urls")),
]
