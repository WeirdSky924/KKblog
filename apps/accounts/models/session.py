import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def session_token_digest(raw_token: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(), raw_token.encode(), hashlib.sha256
    ).hexdigest()


class LoginSession(models.Model):
    class Kind(models.TextChoices):
        STANDARD_12H = "STANDARD_12H", "12 小时"
        REMEMBER_30D = "REMEMBER_30D", "30 天"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        "accounts.Account", related_name="login_sessions", on_delete=models.CASCADE
    )
    token_digest = models.CharField(max_length=64, unique=True)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    created_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    user_agent_summary = models.CharField(max_length=255, blank=True)
    created_ip = models.GenericIPAddressField(protocol="both", unpack_ipv4=True)

    class Meta:
        db_table = "account_login_session"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("created_at")),
                name="login_session_positive_lifetime",
            )
        ]
        indexes = [
            models.Index(
                fields=["account", "revoked_at", "expires_at"],
                name="login_session_active_idx",
            )
        ]

    @classmethod
    def issue(
        cls,
        *,
        account,
        remember: bool,
        client_ip: str = "127.0.0.1",
        user_agent_summary: str = "Unknown browser",
        now=None,
    ) -> tuple[str, "LoginSession"]:
        issued_at = now or timezone.now()
        raw_token = secrets.token_urlsafe(32)
        kind = cls.Kind.REMEMBER_30D if remember else cls.Kind.STANDARD_12H
        lifetime = timedelta(days=30) if remember else timedelta(hours=12)
        session = cls.objects.create(
            account=account,
            token_digest=session_token_digest(raw_token),
            kind=kind,
            created_at=issued_at,
            last_seen_at=issued_at,
            expires_at=issued_at + lifetime,
            user_agent_summary=user_agent_summary[:255],
            created_ip=client_ip,
        )
        return raw_token, session

    def is_active(self, *, now=None) -> bool:
        current = now or timezone.now()
        return self.revoked_at is None and self.expires_at > current

    def rotate_token(self) -> str:
        raw_token = secrets.token_urlsafe(32)
        self.token_digest = session_token_digest(raw_token)
        self.save(update_fields=("token_digest",))
        return raw_token
