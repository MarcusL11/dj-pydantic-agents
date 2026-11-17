"""Model row factories. Use them only in tests that need database rows.

The test settings use the User model of django.contrib.auth.
"""

from django.contrib.auth.models import User
from factory import Sequence
from factory import SubFactory
from factory.django import DjangoModelFactory

from dj_pydantic_agents.models import Attachment
from dj_pydantic_agents.models import Conversation
from dj_pydantic_agents.models import PendingApproval
from dj_pydantic_agents.models import Turn


class UserFactory(DjangoModelFactory[User]):
    username = Sequence(lambda n: f"user-{n}")

    class Meta:
        model = User


class ConversationFactory(DjangoModelFactory[Conversation]):
    agent_name = "assistant"
    owner = SubFactory(UserFactory)

    class Meta:
        model = Conversation


class TurnFactory(DjangoModelFactory[Turn]):
    conversation = SubFactory(ConversationFactory)
    requested_by = SubFactory(UserFactory)
    prompt = "Hi"

    class Meta:
        model = Turn


class PendingApprovalFactory(DjangoModelFactory[PendingApproval]):
    turn = SubFactory(TurnFactory)
    tool_call_id = Sequence(lambda n: f"call-{n}")
    tool_name = "send_mail"
    args_json = '{"to":"ada"}'

    class Meta:
        model = PendingApproval


class AttachmentFactory(DjangoModelFactory[Attachment]):
    """A pending file. Pass turn for a sent file."""

    conversation = SubFactory(ConversationFactory)
    uploaded_by = SubFactory(UserFactory)
    file = Sequence(lambda n: f"dj_pydantic_agents/attachments/file-{n}.pdf")
    name = "invoice.pdf"
    media_type = "application/pdf"
    size = 8
    sha256 = "0" * 64

    class Meta:
        model = Attachment
