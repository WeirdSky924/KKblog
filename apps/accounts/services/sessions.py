from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import LoginSession, SecurityEvent


class SessionError(ValueError):
    pass


def summarize_user_agent(raw_value: str) -> str:
    value = raw_value[:1024]
    if "Edg/" in value:
        browser = "Edge"
    elif "Firefox/" in value:
        browser = "Firefox"
    elif "CriOS/" in value or "Chrome/" in value:
        browser = "Chrome"
    elif "Safari/" in value and "Version/" in value:
        browser = "Safari"
    else:
        browser = "未知浏览器"

    if "iPhone" in value:
        device = "iPhone"
    elif "iPad" in value:
        device = "iPad"
    elif "Android" in value:
        device = "Android"
    elif "Windows" in value:
        device = "Windows"
    elif "Macintosh" in value:
        device = "macOS"
    elif "Linux" in value:
        device = "Linux"
    else:
        device = "未知设备"
    return f"{browser} · {device}"


def _parse_id(value, *, message: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise SessionError(message) from None


def _locked_sessions(*, account_id, session_ids) -> dict[UUID, LoginSession]:
    return {
        row.id: row
        for row in LoginSession.objects.select_for_update().filter(
            account_id=account_id, id__in=session_ids
        )
    }


def _require_active_current(current: LoginSession | None) -> None:
    if current is None or not current.is_active():
        raise SessionError("当前会话已失效")


def revoke_session(
    *,
    account_id,
    current_session_id,
    target_session_id,
    client_ip: str,
    trace_code: str,
) -> int:
    current_id = _parse_id(current_session_id, message="当前会话已失效")
    target_id = _parse_id(target_session_id, message="会话不存在或无权操作")
    with transaction.atomic():
        sessions = _locked_sessions(
            account_id=account_id, session_ids={current_id, target_id}
        )
        current = sessions.get(current_id)
        _require_active_current(current)
        target = sessions.get(target_id)
        if target is None:
            raise SessionError("会话不存在或无权操作")
        if target.revoked_at is not None:
            return 0
        target.revoked_at = timezone.now()
        target.save(update_fields=("revoked_at",))
        SecurityEvent.objects.create(
            event_type="SESSION_REVOKED",
            account_id=account_id,
            client_ip=client_ip,
            trace_code=trace_code,
            safe_summary={"scope": "target", "session_id": str(target.id)},
        )
        return 1


def revoke_all_sessions(
    *,
    account_id,
    current_session_id,
    client_ip: str,
    trace_code: str,
) -> int:
    current_id = _parse_id(current_session_id, message="当前会话已失效")
    with transaction.atomic():
        current = (
            LoginSession.objects.select_for_update()
            .filter(account_id=account_id, id=current_id)
            .first()
        )
        _require_active_current(current)
        now = timezone.now()
        count = LoginSession.objects.filter(
            account_id=account_id, revoked_at__isnull=True
        ).update(revoked_at=now)
        if count:
            SecurityEvent.objects.create(
                event_type="ALL_SESSIONS_REVOKED",
                account_id=account_id,
                client_ip=client_ip,
                trace_code=trace_code,
                safe_summary={"scope": "all", "count": count},
            )
        return count
