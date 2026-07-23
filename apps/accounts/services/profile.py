from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Account, NicknameHistory
from apps.accounts.profile_rules import ValidatedNickname, validate_nickname
from apps.core.ids import normalize_ulid
from apps.core.time.shanghai import to_shanghai
from apps.media.public import (
    BindingInput,
    MediaBindingError,
    MediaPurpose,
    MediaTargetType,
    replace_bindings,
)

NICKNAME_COOLDOWN = timedelta(days=7)
AuditWriter = Callable[..., object]


class ProfileError(ValueError):
    def __init__(self, field: str | None, message: str) -> None:
        self.field = field
        super().__init__(message)


def change_profile(
    *,
    account_id,
    nickname: str | None,
    theme: str,
    avatar_asset_id: str | None,
    client_ip: str,
    trace_code: str,
    audit_writer: AuditWriter,
    now=None,
) -> Account:
    if not callable(audit_writer):
        raise TypeError("audit_writer must be callable")
    try:
        identity = UUID(str(account_id))
    except (TypeError, ValueError):
        raise ProfileError(None, "账户不存在。") from None
    validated_nickname = _validated_nickname(nickname)
    normalized_theme = _normalized_theme(theme)
    normalized_avatar = _normalized_avatar(avatar_asset_id)
    changed_at = now or timezone.now()
    if timezone.is_naive(changed_at):
        raise ProfileError(None, "资料更新时间无效。")

    with transaction.atomic():
        account = (
            Account.objects.select_for_update()
            .filter(pk=identity, status=Account.Status.ACTIVE)
            .first()
        )
        if account is None:
            raise ProfileError(None, "账户不存在。")
        nickname_changed = account.nickname != validated_nickname.display
        theme_changed = account.theme != normalized_theme
        avatar_changed = account.avatar_asset_id != normalized_avatar
        if nickname_changed:
            _require_nickname_available(account, changed_at)
        if avatar_changed:
            _replace_avatar(account, normalized_avatar)
        if not (nickname_changed or theme_changed or avatar_changed):
            return account

        previous_nickname = account.nickname
        before = _audit_state(account)
        account.nickname = validated_nickname.display
        account.normalized_nickname = validated_nickname.normalized
        account.theme = normalized_theme
        account.avatar_asset_id = normalized_avatar
        update_fields = [
            "nickname",
            "normalized_nickname",
            "theme",
            "avatar_asset_id",
            "updated_at",
        ]
        if nickname_changed:
            account.nickname_changed_at = changed_at
            update_fields.append("nickname_changed_at")
        try:
            with transaction.atomic():
                account.save(update_fields=update_fields)
        except IntegrityError:
            raise ProfileError("nickname", "昵称已被使用，请换一个。") from None
        if nickname_changed:
            NicknameHistory.objects.create(
                account=account,
                previous_nickname=previous_nickname,
                nickname=account.nickname,
                changed_at=changed_at,
            )
        audit_writer(
            action="accounts.profile.change",
            actor_id=account.id,
            target_id=str(account.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after=_audit_state(account),
            summary="Change own account profile",
        )
        return account


def _validated_nickname(value: str | None) -> ValidatedNickname:
    try:
        return validate_nickname(value)
    except ValidationError as exc:
        raise ProfileError("nickname", "; ".join(exc.messages)) from None


def _normalized_theme(value: str) -> str:
    mapping = {
        "light": Account.Theme.LIGHT,
        "dark": Account.Theme.DARK,
        "eye-care": Account.Theme.EYE_CARE,
        Account.Theme.LIGHT: Account.Theme.LIGHT,
        Account.Theme.DARK: Account.Theme.DARK,
        Account.Theme.EYE_CARE: Account.Theme.EYE_CARE,
    }
    try:
        return mapping[value]
    except (KeyError, TypeError):
        raise ProfileError("theme", "请选择有效的主题。") from None


def _normalized_avatar(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ProfileError("avatar_asset_id", "头像引用无效，请重新上传。") from None


def _require_nickname_available(account: Account, changed_at) -> None:
    if (
        account.nickname_changed_at is not None
        and changed_at < account.nickname_changed_at + NICKNAME_COOLDOWN
    ):
        available_at = to_shanghai(account.nickname_changed_at + NICKNAME_COOLDOWN)
        raise ProfileError(
            "nickname",
            f"昵称每 7 天可修改一次，请在 {available_at:%Y-%m-%d %H:%M} 后重试。",
        )


def _replace_avatar(account: Account, avatar_asset_id: str | None) -> None:
    inputs = (BindingInput(avatar_asset_id, "avatar"),) if avatar_asset_id else ()
    try:
        replace_bindings(
            actor_id=account.id,
            target_type=MediaTargetType.ACCOUNT_PROFILE,
            target_id=str(account.id),
            inputs=inputs,
            purpose=MediaPurpose.AVATAR,
        )
    except MediaBindingError as exc:
        raise ProfileError("avatar_asset_id", exc.safe_message) from None


def _audit_state(account: Account) -> dict[str, object]:
    return {
        "nickname_present": account.nickname is not None,
        "theme": account.theme,
        "avatar_present": account.avatar_asset_id is not None,
    }


__all__ = [
    "NICKNAME_COOLDOWN",
    "ProfileError",
    "change_profile",
    "validate_nickname",
]
