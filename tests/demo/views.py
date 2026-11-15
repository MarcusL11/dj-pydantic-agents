"""The project pages of the demo. A real project writes the same two views.

The demo signs in a staff user "demo" on the first visit, so that no login
page is necessary.
"""

from django.contrib.auth import login
from django.contrib.auth.models import User
from django.http import Http404
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.views.decorators.http import require_POST

from dj_pydantic_agents.composition import build_conversation_command_service
from dj_pydantic_agents.composition import build_conversation_query_service
from dj_pydantic_agents.dtos.conversation_queries import GetConversationPageQueryDTO
from dj_pydantic_agents.dtos.conversation_queries import ListConversationsQueryDTO
from dj_pydantic_agents.dtos.turn_commands import CreateConversationCommandDTO
from dj_pydantic_agents.errors import ConversationNotFound

AGENT_NAME = "assistant"


def conversation_list(request: HttpRequest) -> HttpResponse:
    conversations = build_conversation_query_service().list_conversations(
        query=ListConversationsQueryDTO(
            user_id=_demo_user_id(request),
            agent_name=AGENT_NAME,
        ),
    )
    return render(request, "demo/list.html", {"conversations": conversations})


@require_POST
def new_conversation(request: HttpRequest) -> HttpResponse:
    created = build_conversation_command_service().create_conversation(
        command=CreateConversationCommandDTO(
            owner_id=_demo_user_id(request),
            agent_name=AGENT_NAME,
        ),
    )
    return redirect("demo:chat", conversation_id=created.conversation_id)


def chat(request: HttpRequest, conversation_id: str) -> HttpResponse:
    try:
        page = build_conversation_query_service().get_conversation_page(
            query=GetConversationPageQueryDTO(
                conversation_id=conversation_id,
                user_id=_demo_user_id(request),
            ),
        )
    except ConversationNotFound as error:
        raise Http404 from error
    return render(request, "demo/chat.html", {"page": page})


def _demo_user_id(request: HttpRequest) -> int:
    if not request.user.is_authenticated:
        user, _ = User.objects.get_or_create(
            username="demo",
            defaults={"is_staff": True},
        )
        login(request, user)
    return request.user.pk  # type: ignore[return-value]
