"""The ChatGPT plan tokens of each user, and the logins that wait for a paste."""

from django.conf import settings
from django.db import models

from dj_pydantic_agents.ids import ID_LENGTH
from dj_pydantic_agents.ids import new_plan_credential_id
from dj_pydantic_agents.ids import new_plan_login_id


class PlanCredential(models.Model):
    id = models.CharField(
        verbose_name="identifier",
        help_text="Prefixed ULID of this credential, for example pcr_01m7f5c8m8x.",
        primary_key=True,
        max_length=ID_LENGTH,
        default=new_plan_credential_id,
        editable=False,
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="user",
        help_text="The user whose ChatGPT plan the agents use.",
        on_delete=models.CASCADE,
        related_name="agent_plan_credential",
    )
    encrypted_tokens = models.TextField(
        verbose_name="encrypted tokens",
        help_text="The tokens, the account and the user, as Fernet-encrypted JSON.",
    )
    account_id = models.CharField(
        verbose_name="account identifier",
        help_text="The ChatGPT account of the tokens.",
        max_length=200,
    )
    refresh_lease_until = models.DateTimeField(
        verbose_name="refresh lease until",
        help_text="A worker refreshes the tokens until this time. Null when none does.",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        verbose_name="created at",
        help_text="Time of the first login.",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        verbose_name="updated at",
        help_text="Time of the latest login or token refresh.",
        auto_now=True,
    )

    class Meta:
        verbose_name = "plan credential"
        verbose_name_plural = "plan credentials"

    def __str__(self) -> str:
        return f"{self.account_id} ({self.user_id})"


class PlanLogin(models.Model):
    id = models.CharField(
        verbose_name="identifier",
        help_text="Prefixed ULID of this login, for example plg_01m7f5c8m8x.",
        primary_key=True,
        max_length=ID_LENGTH,
        default=new_plan_login_id,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="user",
        help_text="The user who started the login.",
        on_delete=models.CASCADE,
        related_name="agent_plan_logins",
    )
    state = models.CharField(
        verbose_name="state",
        help_text="The OAuth state. The pasted address must hold the same value.",
        max_length=200,
        unique=True,
    )
    code_verifier = models.CharField(
        verbose_name="code verifier",
        help_text="The PKCE verifier that the code exchange sends.",
        max_length=200,
    )
    expires_at = models.DateTimeField(
        verbose_name="expires at",
        help_text="After this time, the login cannot complete.",
    )
    created_at = models.DateTimeField(
        verbose_name="created at",
        help_text="Time the login started.",
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "plan login"
        verbose_name_plural = "plan logins"

    def __str__(self) -> str:
        return str(self.id)
