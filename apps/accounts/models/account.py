import uuid

from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models
from django.db.models.functions import Lower

from apps.accounts.profile_rules import validate_nickname
from apps.core.ids import normalize_ulid


def normalize_email(value: str) -> str:
    normalized = value.strip().casefold()
    validate_email(normalized)
    return normalized


def normalize_nickname(value: str | None) -> str | None:
    return validate_nickname(value).normalized


class AccountManager(models.Manager):
    def create_account(
        self,
        *,
        email: str,
        password: str,
        nickname: str | None = None,
        must_change_password: bool = False,
    ) -> "Account":
        account = self.model(
            email=normalize_email(email),
            nickname=nickname.strip() if nickname and nickname.strip() else None,
            must_change_password=must_change_password,
        )
        account.set_password(password)
        account.clean()
        account.save(force_insert=True)
        return account


class Account(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "启用"
        DISABLED = "DISABLED", "禁用"

    class Theme(models.TextChoices):
        LIGHT = "LIGHT", "浅色"
        DARK = "DARK", "深色"
        EYE_CARE = "EYE_CARE", "护眼"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.CharField(max_length=254)
    password_hash = models.CharField(max_length=128)
    nickname = models.CharField(max_length=16, null=True, blank=True)
    normalized_nickname = models.TextField(null=True, blank=True, editable=False)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE
    )
    theme = models.CharField(max_length=16, choices=Theme.choices, default=Theme.LIGHT)
    auto_republish_enabled = models.BooleanField(default=False)
    article_explanation_auto_accept = models.BooleanField(default=False)
    attachment_upload_enabled = models.BooleanField(default=False)
    author_permission_requested_at = models.DateTimeField(
        null=True, blank=True, editable=False
    )
    avatar_asset_id = models.CharField(max_length=26, null=True, blank=True)
    nickname_changed_at = models.DateTimeField(null=True, blank=True)
    must_change_password = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AccountManager()

    class Meta:
        db_table = "account"
        constraints = [
            models.UniqueConstraint(Lower("email"), name="account_email_ci_unique"),
            models.UniqueConstraint(
                fields=["normalized_nickname"],
                condition=models.Q(normalized_nickname__isnull=False),
                name="account_nickname_casefold_unique",
            ),
        ]

    def clean(self) -> None:
        self.email = normalize_email(self.email)
        nickname = validate_nickname(self.nickname)
        self.nickname = nickname.display
        self.normalized_nickname = nickname.normalized
        if self.avatar_asset_id:
            try:
                self.avatar_asset_id = normalize_ulid(self.avatar_asset_id)
            except (TypeError, ValueError):
                raise ValidationError({"avatar_asset_id": "头像引用无效。"}) from None
        else:
            self.avatar_asset_id = None

    def save(self, *args, **kwargs) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def set_password(self, raw_password: str) -> None:
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password(raw_password, self.password_hash)

    def delete(self, *args, **kwargs):
        if self.roles.filter(role="ADMINISTRATOR").exists():
            raise ValidationError("唯一管理员账户不能删除")
        return super().delete(*args, **kwargs)
