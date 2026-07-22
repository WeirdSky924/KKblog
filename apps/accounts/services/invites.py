import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import InviteCode, RoleAssignment
from apps.core.ids import new_ulid

CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
VALIDITY_DAYS = frozenset({1, 3, 7, 30})


class InviteError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class IssuedInvite:
    id: UUID
    raw_code: str
    display_suffix: str
    expires_at: datetime


def invite_digest(raw_code: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f"invite:{raw_code}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _require_admin(actor_id) -> None:
    if not RoleAssignment.objects.filter(
        account_id=actor_id,
        account__status="ACTIVE",
        role=RoleAssignment.Role.ADMINISTRATOR,
    ).exists():
        raise PermissionError("Administrator access required")


def _raw_code() -> str:
    return "".join(secrets.choice(CROCKFORD_ALPHABET) for _ in range(16))


def validate_invite(*, raw_code: str, now=None) -> InviteCode:
    if not isinstance(raw_code, str) or len(raw_code.strip()) != 16:
        raise InviteError("邀请码无效或已失效")
    invite = InviteCode.objects.filter(
        code_digest=invite_digest(raw_code.strip().upper())
    ).first()
    if invite is None or invite.state(now=now or timezone.now()) != "ACTIVE":
        raise InviteError("邀请码无效或已失效")
    return invite


def generate_invite_codes(
    *,
    count: int,
    validity_days: int,
    actor_id,
    trace_code: str,
    client_ip: str,
    audit_writer,
    now=None,
) -> tuple[IssuedInvite, ...]:
    _require_admin(actor_id)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 1000:
        raise InviteError("生成数量必须在 1 到 1000 之间")
    if validity_days not in VALIDITY_DAYS:
        raise InviteError("邀请码有效期无效")
    current = now or timezone.now()
    expires_at = current + timedelta(days=validity_days)
    raw_codes: set[str] = set()
    while len(raw_codes) < count:
        raw_codes.add(_raw_code())
    batch_id = new_ulid()
    with transaction.atomic():
        invites = [
            InviteCode(
                code_digest=invite_digest(raw_code),
                display_suffix=raw_code[-4:],
                expires_at=expires_at,
                created_by_id=actor_id,
                created_at=current,
            )
            for raw_code in raw_codes
        ]
        try:
            InviteCode.objects.bulk_create(invites)
        except IntegrityError as exc:
            raise InviteError("邀请码生成冲突，请重试") from exc
        audit_writer(
            action="accounts.invite.generate",
            actor_id=actor_id,
            target_id=batch_id,
            trace_code=trace_code,
            client_ip=client_ip,
            before={},
            after={"count": count, "validity_days": validity_days},
            summary="invite batch generated",
        )
    by_digest = {invite.code_digest: invite for invite in invites}
    return tuple(
        IssuedInvite(
            id=by_digest[invite_digest(raw_code)].id,
            raw_code=raw_code,
            display_suffix=raw_code[-4:],
            expires_at=expires_at,
        )
        for raw_code in sorted(raw_codes)
    )


def redeem_invite(*, raw_code: str, account_id, now=None) -> InviteCode:
    current = now or timezone.now()
    with transaction.atomic():
        invite = (
            InviteCode.objects.select_for_update()
            .filter(code_digest=invite_digest(raw_code.strip().upper()))
            .first()
        )
        if invite is None or invite.state(now=current) != "ACTIVE":
            raise InviteError("邀请码无效或已失效")
        invite.redeemed_by_id = account_id
        invite.redeemed_at = current
        invite.save(update_fields=("redeemed_by", "redeemed_at"))
        return invite


def revoke_invites(
    *,
    invite_ids,
    actor_id,
    trace_code: str,
    client_ip: str,
    audit_writer,
    now=None,
) -> int:
    _require_admin(actor_id)
    ids = tuple(dict.fromkeys(UUID(str(value)) for value in invite_ids))
    if not ids or len(ids) > 1000:
        raise InviteError("撤销范围无效")
    current = now or timezone.now()
    with transaction.atomic():
        invites = list(
            InviteCode.objects.select_for_update().filter(pk__in=ids).order_by("id")
        )
        if len(invites) != len(ids) or any(
            invite.state(now=current) != "ACTIVE" for invite in invites
        ):
            raise InviteError("仅可撤销仍有效且未使用的邀请码")
        for invite in invites:
            invite.revoked_at = current
            invite.save(update_fields=("revoked_at",))
            audit_writer(
                action="accounts.invite.revoke",
                actor_id=actor_id,
                target_id=str(invite.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before={"state": "ACTIVE"},
                after={"state": "REVOKED"},
                summary="invite revoked",
            )
    return len(invites)
