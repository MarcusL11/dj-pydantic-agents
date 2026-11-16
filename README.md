# dj-pydantic-agents

Agent turns, streaming and approvals for Django. Not the same package as [`django-pydantic-ai`](https://github.com/hartungstenio/django-pydantic-ai), which stores memory and conversations.

## Status

Version 0.1 is complete. Vintage Eye is the first project that uses it. It has no production use yet.

## Needs

- Python 3.14 or later
- Django 6.0 or later
- PostgreSQL
- Redis, for the Redis Stream transport
- `pydantic-ai-slim==2.68.*` and `pydantic-ai-harness==0.68.*`

## Install

Install the package from PyPI. Select the extras that the project uses: `celery`, `codex` and `datastar`.

```bash
uv add "dj-pydantic-agents[celery,codex,datastar]==0.2.1"
```

## Celery

Install the extra: `dj-pydantic-agents[celery]`. Then add the app and the task runner:

```python
INSTALLED_APPS = [
    ...,
    "dj_pydantic_agents",
    "dj_pydantic_agents.contrib.celery",
]

DJ_PYDANTIC_AGENTS = {
    ...,
    "TASK_RUNNER": "dj_pydantic_agents.contrib.celery.runner.CeleryTaskRunner",
    "CELERY_QUEUE": "agents",  # Optional. The default is the default Celery queue.
}
```

The worker finds the turn task through `app.autodiscover_tasks()`. Without the app in `INSTALLED_APPS`, the worker does not know the task, and the check `dj_pydantic_agents.E006` fails.

The task uses the Celery time limits of the project. A turn can take more time than other tasks. To set the limits for the turn task only, use `CELERY_TASK_ANNOTATIONS`:

```python
CELERY_TASK_ANNOTATIONS = {
    "dj_pydantic_agents.run_turn": {"soft_time_limit": 600, "time_limit": 660},
}
```

## Datastar

Install the extra: `dj-pydantic-agents[datastar]`. The app has three views: send a message, decide an approval, and stream a turn. Each view returns Datastar patches. The project writes each full page.

```python
INSTALLED_APPS = [
    ...,
    "dj_pydantic_agents",
    "dj_pydantic_agents.contrib.datastar",
]

DJ_PYDANTIC_AGENTS = {
    ...,
    # A queued or running turn with no status change for this time lost its
    # worker. The stream view then fails it with worker_lost. Make it longer
    # than the hard time limit of the turn task.
    "STALE_TURN_SECONDS": 1800,  # The default.
}
```

Include the URLs. The namespace is `dj_pydantic_agents`:

```python
urlpatterns = [
    ...,
    path("agents/", include("dj_pydantic_agents.contrib.datastar.urls")),
]
```

The stream view streams. Serve the project with an ASGI server, for example uvicorn. `runserver` cannot stream.

Keep `CONN_MAX_AGE` at 0, the default, in `DATABASES`. The Django documentation says to disable persistent connections in async mode. Use the PostgreSQL pool of Django if you need a pool. The views free their database connection before the stream waits for events.

### The project pages

The project writes the chat page and the "New conversation" view. Each view calls one service:

```python
from dj_pydantic_agents.composition import build_conversation_command_service
from dj_pydantic_agents.composition import build_conversation_query_service
from dj_pydantic_agents.dtos.conversation_queries import GetConversationPageQueryDTO
from dj_pydantic_agents.dtos.turn_commands import CreateConversationCommandDTO


@staff_member_required
@require_POST
def new_conversation(request):
    created = build_conversation_command_service().create_conversation(
        command=CreateConversationCommandDTO(owner_id=request.user.pk, agent_name="assistant"),
    )
    return redirect("dashboard:agent_chat", conversation_id=created.conversation_id)


@staff_member_required
def agent_chat(request, conversation_id):
    page = build_conversation_query_service().get_conversation_page(
        query=GetConversationPageQueryDTO(conversation_id=conversation_id, user_id=request.user.pk),
    )
    return render(request, "dashboard/agent_chat.html", {"page": page})
```

`list_conversations()` of the query service gives the conversations of a user with an agent, newest first.

The page template loads Datastar 1 and includes the chat:

```django
{% include "dj_pydantic_agents/chat.html" %}
```

The template needs `page` and `csrf_token` in the context. `render()` adds `csrf_token`. Each package form sends the token in the `X-CSRFToken` header, so the package does not need `django-datastar`.

A Cotton project can wrap the include in a component, for example `templates/cotton/agent_chat.html`:

```django
{% include "dj_pydantic_agents/chat.html" %}
```

Then the page uses `<c-agent-chat :page="page" />`.

### Templates and class names

The templates are plain Django templates in `dj_pydantic_agents/`: `chat.html`, `transcript_line.html`, `reply.html`, `run_end.html`, `approval_card.html` and `message_form.html`. To change one, put a template at the same path in the `templates/` folder of the project. An override of `approval_card.html` must keep the partial `actions`.

The package has no CSS. Style these classes:

- `djpa-chat`, `djpa-chat__scroll` (the scroll pane), `djpa-transcript`
- `djpa-line` with `djpa-line--user`, `djpa-line--assistant`, `djpa-line--tool-call`, `djpa-line--tool-result` or `djpa-line--error`, and `djpa-line__tool`, `djpa-line__data`
- `djpa-reply`, `djpa-reply__text`
- `djpa-approval`, `djpa-approval__tool`, `djpa-approval__args`, `djpa-approval__actions`, `djpa-approval__form`, `djpa-approval__approve`, `djpa-approval__deny`, `djpa-approval__decision`
- `djpa-message-form`, `djpa-message-form__input`, `djpa-message-form__send`

A chat with a fixed size and a scroll pane needs four rules. With `column-reverse`, the browser keeps the view at the newest line, with no JavaScript:

```css
.djpa-chat { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.djpa-chat__scroll { flex: 1; min-height: 0; display: flex; flex-direction: column-reverse; overflow-y: auto; }
.djpa-message-form { flex: none; display: flex; }
.djpa-message-form__input { flex: 1; min-width: 0; }
```

The parent of `djpa-chat` must have a fixed height, for example `100dvh` minus the header. `tests/demo/templates/demo/base.html` has a full responsive example.

### The demo

`tests/demo/` is a small project for a test in a browser. It uses the Redis transport, a scripted model and a thread task runner:

```bash
docker compose up -d
uv run django-admin migrate --settings=tests.demo.settings --pythonpath=.
uv run --with uvicorn uvicorn tests.demo.asgi:application --port 8001
```

Then open http://127.0.0.1:8001/.

## Codex: the ChatGPT plan of each user

Install the extra: `dj-pydantic-agents[codex]`. Each user connects their own ChatGPT plan. The turns of that user then use the `openai-codex` provider of Pydantic AI with the tokens of that user.

```python
INSTALLED_APPS = [
    ...,
    "dj_pydantic_agents",
    "dj_pydantic_agents.contrib.codex",
]

DJ_PYDANTIC_AGENTS = {
    ...,
    "MODEL_FACTORY": "dj_pydantic_agents.contrib.codex.model_factory.CodexModelFactory",
    "MODEL_NAMES": {"chat": "gpt-6.1-sol", "summary": "gpt-6-luna"},
    # Fernet keys. The first key encrypts, each key decrypts. Keep them out of the code.
    "CODEX_TOKEN_KEYS": env.list("CODEX_TOKEN_KEYS"),
}
```

Make a key with this command:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

To change the key, put the new key first and keep the old key second. A login or a token refresh then encrypts with the new key. The check `dj_pydantic_agents.E007` finds a missing or bad key.

The encrypted value also holds the user ID. A copy of the value to the row of another user does not decrypt.

### The login pages

The login uses a copy and paste of an address. After the sign-in, the browser opens `http://localhost:1455/auth/callback?code=...`. That page does not load on a server. The user copies its address into a form. A login must complete in 10 minutes.

The project writes the two pages. Each view calls one service:

```python
from dj_pydantic_agents.contrib.codex.composition import build_plan_login_service
from dj_pydantic_agents.contrib.codex.dtos import CompletePlanLoginCommandDTO
from dj_pydantic_agents.contrib.codex.dtos import StartPlanLoginCommandDTO
from dj_pydantic_agents.contrib.codex.errors import PlanLoginFailed


@staff_member_required
def plan_login(request, error=""):
    started = build_plan_login_service().start_login(
        command=StartPlanLoginCommandDTO(user_id=request.user.pk),
    )
    return render(
        request,
        "dashboard/plan_login.html",
        {
            "authorization_url": started.authorization_url,
            "form_action": reverse("dashboard:plan_login_complete"),
            "error": error,
        },
    )


@staff_member_required
@require_POST
def plan_login_complete(request):
    try:
        build_plan_login_service().complete_login(
            command=CompletePlanLoginCommandDTO(
                user_id=request.user.pk,
                pasted_url=request.POST.get("pasted_url", ""),
            ),
        )
    except PlanLoginFailed as error:
        return plan_login(request, error=str(error))
    return redirect("dashboard:agent_chat_list")
```

`get_plan_status()` tells if the user saved a plan, and gives the account ID. It reads only the saved row. It does not decrypt the tokens and makes no request, so a token that OpenAI revoked still shows as connected. The next turn then fails with `plan_not_connected`.

```python
from dj_pydantic_agents.contrib.codex.dtos import GetPlanStatusQueryDTO

status = build_plan_login_service().get_plan_status(
    query=GetPlanStatusQueryDTO(user_id=request.user.pk),
)
# status.connected: bool, status.account_id: str | None
```

The page template includes the form:

```django
{% include "dj_pydantic_agents/codex/login_form.html" %}
```

The form classes are `djpa-codex-login`, with `__steps`, `__link`, `__error`, `__form`, `__input` and `__submit`.

### The tokens in the workers

- A turn of a user with no login fails with the code `plan_not_connected`.
- A refresh token works one time. Before a refresh, a worker takes a lease of 30 seconds on the row of the user. Another worker waits, then uses the new tokens.
- The provider does not use background mode, because the backend cannot resume a background response.
- The model names in `MODEL_NAMES` go to the backend unchanged. The backend accepts or refuses them.

## Development

```bash
uv sync --all-extras
docker compose up -d
uv run pytest
```

PostgreSQL runs in Docker on host port 5433, and Redis on host port 6380.
