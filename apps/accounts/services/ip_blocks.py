from collections.abc import Callable
from ipaddress import ip_address

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Account, IpBlock, RoleAssignment, SecurityEvent
from apps.accounts.network import (
    ClientIpError,
    network_subject_digest,
    normalize_ip,
)


class IpBlockError(RuntimeError):
    pass


AuditWriter = Callable[..., object]


def _administrator(actor_id) -> Account:
    actor = (
        Account.objects.filter(pk=actor_id, status=Account.Status.ACTIVE).first()
        if actor_id
        else None
    )
    if (
        actor is None
        or not RoleAssignment.objects.filter(
            account=actor, role=RoleAssignment.Role.ADMINISTRATOR
        ).exists()
    ):
        raise PermissionError("Administrator access required")
    return actor


def _target_address(value: str, *, current_address: str) -> str:
    try:
        normalized = normalize_ip(value)
        current = normalize_ip(current_address)
    except ClientIpError:
        raise IpBlockError("IP 地址无效") from None
    parsed = ip_address(normalized)
    if parsed.is_unspecified or parsed.is_loopback or parsed.is_multicast:
        raise IpBlockError("不能封禁服务器或无效网络地址")
    if normalized == current:
        raise IpBlockError("不能封禁当前管理连接的 IP")
    return normalized


def _note(value: str) -> str:
    if not isinstance(value, str):
        raise IpBlockError("备注无效")
    normalized = value.strip()
    if len(normalized) > 500 or "\x00" in normalized:
        raise IpBlockError("备注无效")
    return normalized


def block_ip(
    *,
    address: str,
    note: str,
    actor_id,
    client_ip: str,
    trace_code: str,
    audit_writer: AuditWriter,
) -> IpBlock:
    actor = _administrator(actor_id)
    target = _target_address(address, current_address=client_ip)
    safe_note = _note(note)
    try:
        with transaction.atomic():
            if (
                IpBlock.objects.select_for_update()
                .filter(address=target, unblocked_at__isnull=True)
                .exists()
            ):
                raise IpBlockError("该 IP 已被封禁")
            row = IpBlock(
                address=target,
                note=safe_note,
                created_by=actor,
            )
            try:
                row.full_clean()
                row.save(force_insert=True)
            except ValidationError as exc:
                raise IpBlockError("IP 封禁信息无效") from exc
            audit_writer(
                action="accounts.ip_block.block",
                actor_id=actor.id,
                target_id=row.id,
                trace_code=trace_code,
                client_ip=client_ip,
                before={"active": False, "note_present": False},
                after={"active": True, "note_present": bool(safe_note)},
                summary="Block network address",
            )
            SecurityEvent.objects.create(
                event_type="IP_BLOCK_APPLIED",
                account=actor,
                subject_digest=network_subject_digest(target),
                client_ip=client_ip,
                trace_code=trace_code,
                safe_summary={"action": "blocked"},
            )
            return row
    except IntegrityError:
        raise IpBlockError("该 IP 已被封禁") from None


def unblock_ip(
    *,
    block_id: str,
    actor_id,
    client_ip: str,
    trace_code: str,
    audit_writer: AuditWriter,
) -> IpBlock:
    actor = _administrator(actor_id)
    with transaction.atomic():
        try:
            row = IpBlock.objects.select_for_update().get(pk=block_id)
        except (IpBlock.DoesNotExist, ValidationError):
            raise IpBlockError("封禁记录不存在") from None
        if row.unblocked_at is not None:
            return row
        row.unblocked_at = timezone.now()
        row.unblocked_by = actor
        row.save(update_fields=("unblocked_at", "unblocked_by"))
        audit_writer(
            action="accounts.ip_block.unblock",
            actor_id=actor.id,
            target_id=row.id,
            trace_code=trace_code,
            client_ip=client_ip,
            before={"active": True},
            after={"active": False},
            summary="Unblock network address",
        )
        SecurityEvent.objects.create(
            event_type="IP_BLOCK_REMOVED",
            account=actor,
            subject_digest=network_subject_digest(row.address),
            client_ip=client_ip,
            trace_code=trace_code,
            safe_summary={"action": "unblocked"},
        )
        return row
