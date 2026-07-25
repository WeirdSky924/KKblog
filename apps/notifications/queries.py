from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core import signing
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from apps.core.ids import normalize_ulid
from apps.notifications.models import Notification, NotificationReceipt
from apps.notifications.services.broadcast import BROADCAST_TEMPLATE_KEY
from apps.notifications.templates_registry import render_notification

_CURSOR_SALT = "notifications.inbox-cursor.v1"


class NotificationCursorError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RecipientNotification:
    notification_id: str
    template_key: str
    actor_id: str | None
    target_type: str
    target_id: str
    payload_safe: dict[str, object]
    read_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class NotificationItem:
    notification_id: str
    title: str
    message: str
    target_url: str | None
    is_read: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class NotificationPopover:
    items: tuple[NotificationItem, ...]
    unread_count: int


@dataclass(frozen=True, slots=True)
class NotificationInboxPage:
    items: tuple[NotificationItem, ...]
    next_cursor: str | None
    start_index: int


@dataclass(frozen=True, slots=True)
class BroadcastSummary:
    notification_id: str
    headline: str
    message: str
    state: str
    recipient_count: int
    read_count: int
    unread_count: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class BroadcastRecipient:
    recipient_id: str
    display_name: str
    email: str
    is_read: bool
    read_at: datetime | None


@dataclass(frozen=True, slots=True)
class BroadcastDetail:
    notification_id: str
    headline: str
    message: str
    state: str
    recipient_count: int
    read_count: int
    unread_count: int
    created_at: datetime
    hidden_at: datetime | None
    deleted_at: datetime | None
    recipients: tuple[BroadcastRecipient, ...]
    recipient_total: int
    recipient_page: int
    recipient_pages: int


def _recipient_id(value: UUID | str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ValueError("Invalid notification recipient") from None


def _require_broadcast_admin(is_admin: bool) -> None:
    if is_admin is not True:
        raise PermissionError("Broadcast access denied")


def _broadcast_state(notification: Notification) -> str:
    if notification.deleted_at is not None:
        return "DELETED"
    if notification.hidden_at is not None:
        return "HIDDEN"
    return "VISIBLE"


def _broadcast_query():
    return Notification.objects.filter(template_key=BROADCAST_TEMPLATE_KEY).annotate(
        recipient_count_value=Count("receipts"),
        read_count_value=Count("receipts", filter=Q(receipts__read_at__isnull=False)),
    )


def _broadcast_summary(notification: Notification) -> BroadcastSummary:
    rendered = render_notification(notification.template_key, notification.payload_safe)
    recipient_count = notification.recipient_count_value
    read_count = notification.read_count_value
    return BroadcastSummary(
        notification_id=notification.id,
        headline=rendered.title,
        message=rendered.message,
        state=_broadcast_state(notification),
        recipient_count=recipient_count,
        read_count=read_count,
        unread_count=recipient_count - read_count,
        created_at=notification.created_at,
    )


def broadcast_list(*, is_admin: bool, limit: int = 50) -> tuple[BroadcastSummary, ...]:
    _require_broadcast_admin(is_admin)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200:
        raise ValueError("Invalid broadcast list limit")
    return tuple(
        _broadcast_summary(notification)
        for notification in _broadcast_query().order_by("-created_at", "-id")[:limit]
    )


def broadcast_detail(
    *,
    notification_id: str,
    is_admin: bool,
    recipient_state: str = "",
    keyword: str = "",
    page: int = 1,
    page_size: int = 50,
) -> BroadcastDetail:
    _require_broadcast_admin(is_admin)
    try:
        normalized_id = normalize_ulid(notification_id)
    except (TypeError, ValueError):
        raise PermissionError("Broadcast access denied") from None
    state = recipient_state.strip().upper()
    if state not in {"", "READ", "UNREAD"}:
        raise ValueError("Invalid broadcast recipient state")
    if not isinstance(keyword, str) or len(keyword) > 200:
        raise ValueError("Invalid broadcast recipient keyword")
    normalized_keyword = keyword.strip()
    if (
        not isinstance(page, int)
        or isinstance(page, bool)
        or page < 1
        or not isinstance(page_size, int)
        or isinstance(page_size, bool)
        or not 1 <= page_size <= 100
    ):
        raise ValueError("Invalid broadcast recipient page")
    notification = _broadcast_query().filter(pk=normalized_id).first()
    if notification is None:
        raise PermissionError("Broadcast access denied")
    receipts = notification.receipts.select_related("recipient")
    if state == "READ":
        receipts = receipts.filter(read_at__isnull=False)
    elif state == "UNREAD":
        receipts = receipts.filter(read_at__isnull=True)
    if normalized_keyword:
        receipts = receipts.filter(
            Q(recipient__email__icontains=normalized_keyword)
            | Q(recipient__nickname__icontains=normalized_keyword)
        )
    receipts = receipts.order_by("recipient__created_at", "recipient_id")
    recipient_total = receipts.count()
    recipient_pages = max(1, (recipient_total + page_size - 1) // page_size)
    if page > recipient_pages:
        raise ValueError("Invalid broadcast recipient page")
    offset = (page - 1) * page_size
    rows = tuple(receipts[offset : offset + page_size])
    summary = _broadcast_summary(notification)
    return BroadcastDetail(
        notification_id=summary.notification_id,
        headline=summary.headline,
        message=summary.message,
        state=summary.state,
        recipient_count=summary.recipient_count,
        read_count=summary.read_count,
        unread_count=summary.unread_count,
        created_at=notification.created_at,
        hidden_at=notification.hidden_at,
        deleted_at=notification.deleted_at,
        recipients=tuple(
            BroadcastRecipient(
                recipient_id=str(row.recipient_id),
                display_name=row.recipient.nickname or row.recipient.email,
                email=row.recipient.email,
                is_read=row.read_at is not None,
                read_at=row.read_at,
            )
            for row in rows
        ),
        recipient_total=recipient_total,
        recipient_page=page,
        recipient_pages=recipient_pages,
    )


def _visible_receipts(recipient_id: UUID):
    return NotificationReceipt.objects.select_related("notification").filter(
        recipient_id=recipient_id,
        notification__hidden_at__isnull=True,
        notification__deleted_at__isnull=True,
    )


def _target_url(target_type: str, target_id: str) -> str | None:
    if target_type == "article":
        return reverse("article:detail", kwargs={"article_id": target_id})
    if target_type == "tag":
        return reverse("public:tag", kwargs={"tag_id": target_id})
    if target_type == "account_role":
        return reverse("accounts:settings")
    return None


def _item(receipt: NotificationReceipt) -> NotificationItem:
    notification = receipt.notification
    rendered = render_notification(notification.template_key, notification.payload_safe)
    return NotificationItem(
        notification_id=notification.id,
        title=rendered.title,
        message=rendered.message,
        target_url=_target_url(notification.target_type, notification.target_id),
        is_read=receipt.read_at is not None,
        created_at=notification.created_at,
    )


def unread_notification_count(*, recipient_id: UUID | str) -> int:
    identity = _recipient_id(recipient_id)
    return _visible_receipts(identity).filter(read_at__isnull=True).count()


def notification_popover(
    *, recipient_id: UUID | str, limit: int = 5
) -> NotificationPopover:
    identity = _recipient_id(recipient_id)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 5:
        raise ValueError("Invalid notification popover limit")
    rows = tuple(
        _visible_receipts(identity).order_by(
            "-notification__created_at", "-notification_id"
        )[:limit]
    )
    return NotificationPopover(
        items=tuple(_item(row) for row in rows),
        unread_count=unread_notification_count(recipient_id=identity),
    )


def _aware(value: object) -> datetime:
    if not isinstance(value, str):
        raise NotificationCursorError("Invalid notification cursor")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise NotificationCursorError("Invalid notification cursor") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise NotificationCursorError("Invalid notification cursor")
    return parsed


def _cursor_position(
    token: str | None, *, recipient_id: UUID
) -> tuple[datetime, datetime | None, str | None, int]:
    if token is None:
        return timezone.now(), None, None, 0
    if not isinstance(token, str) or not token or len(token) > 2048:
        raise NotificationCursorError("Invalid notification cursor")
    try:
        payload = signing.loads(token, salt=_CURSOR_SALT)
    except signing.BadSignature:
        raise NotificationCursorError("Invalid notification cursor") from None
    if not isinstance(payload, dict) or set(payload) != {
        "v",
        "recipient_id",
        "snapshot_at",
        "created_at",
        "id",
        "offset",
    }:
        raise NotificationCursorError("Invalid notification cursor")
    if payload["v"] != 1 or payload["recipient_id"] != str(recipient_id):
        raise NotificationCursorError("Invalid notification cursor")
    try:
        notification_id = normalize_ulid(payload["id"])
    except (TypeError, ValueError):
        raise NotificationCursorError("Invalid notification cursor") from None
    offset = payload["offset"]
    if (
        not isinstance(offset, int)
        or isinstance(offset, bool)
        or not 1 <= offset <= 10_000_000
    ):
        raise NotificationCursorError("Invalid notification cursor")
    return (
        _aware(payload["snapshot_at"]),
        _aware(payload["created_at"]),
        notification_id,
        offset,
    )


def _next_cursor(
    *,
    recipient_id: UUID,
    snapshot: datetime,
    receipt: NotificationReceipt,
    offset: int,
) -> str:
    return signing.dumps(
        {
            "v": 1,
            "recipient_id": str(recipient_id),
            "snapshot_at": snapshot.isoformat(),
            "created_at": receipt.notification.created_at.isoformat(),
            "id": receipt.notification_id,
            "offset": offset,
        },
        salt=_CURSOR_SALT,
        compress=True,
    )


def notification_inbox(
    *,
    recipient_id: UUID | str,
    cursor: str | None = None,
    page_size: int = 20,
) -> NotificationInboxPage:
    identity = _recipient_id(recipient_id)
    if (
        not isinstance(page_size, int)
        or isinstance(page_size, bool)
        or not 1 <= page_size <= 50
    ):
        raise ValueError("Invalid notification page size")
    snapshot, created_at, notification_id, offset = _cursor_position(
        cursor, recipient_id=identity
    )
    query = _visible_receipts(identity).filter(notification__created_at__lte=snapshot)
    if created_at is not None and notification_id is not None:
        query = query.filter(
            Q(notification__created_at__lt=created_at)
            | Q(
                notification__created_at=created_at,
                notification_id__lt=notification_id,
            )
        )
    fetched = tuple(
        query.order_by("-notification__created_at", "-notification_id")[: page_size + 1]
    )
    rows = fetched[:page_size]
    return NotificationInboxPage(
        items=tuple(_item(row) for row in rows),
        next_cursor=(
            _next_cursor(
                recipient_id=identity,
                snapshot=snapshot,
                receipt=rows[-1],
                offset=offset + len(rows),
            )
            if len(fetched) > page_size
            else None
        ),
        start_index=offset,
    )


def notification_detail(
    *, recipient_id: UUID | str, notification_id: str
) -> NotificationItem:
    identity = _recipient_id(recipient_id)
    try:
        normalized_id = normalize_ulid(notification_id)
    except (TypeError, ValueError):
        raise PermissionError("Notification access denied") from None
    receipt = _visible_receipts(identity).filter(notification_id=normalized_id).first()
    if receipt is None:
        raise PermissionError("Notification access denied")
    return _item(receipt)


def notifications_for_recipient(
    *, recipient_id: UUID | str, limit: int = 100
) -> list[RecipientNotification]:
    if not 1 <= limit <= 200:
        raise ValueError("Invalid notification query limit")
    rows = (
        NotificationReceipt.objects.select_related("notification")
        .filter(
            recipient_id=recipient_id,
            notification__hidden_at__isnull=True,
            notification__deleted_at__isnull=True,
        )
        .order_by("-notification__created_at", "-notification_id")[:limit]
    )
    return [
        RecipientNotification(
            notification_id=row.notification_id,
            template_key=row.notification.template_key,
            actor_id=(
                str(row.notification.actor_id) if row.notification.actor_id else None
            ),
            target_type=row.notification.target_type,
            target_id=row.notification.target_id,
            payload_safe=row.notification.payload_safe,
            read_at=row.read_at,
            created_at=row.notification.created_at,
        )
        for row in rows
    ]


def notification_for_recipient(
    *, notification_id: str, recipient_id: UUID | str
) -> RecipientNotification:
    row = (
        NotificationReceipt.objects.select_related("notification")
        .filter(
            notification_id=notification_id,
            recipient_id=recipient_id,
            notification__hidden_at__isnull=True,
            notification__deleted_at__isnull=True,
        )
        .first()
    )
    if row is None:
        raise PermissionError("Notification access denied")
    return RecipientNotification(
        notification_id=row.notification_id,
        template_key=row.notification.template_key,
        actor_id=(
            str(row.notification.actor_id) if row.notification.actor_id else None
        ),
        target_type=row.notification.target_type,
        target_id=row.notification.target_id,
        payload_safe=row.notification.payload_safe,
        read_at=row.read_at,
        created_at=row.notification.created_at,
    )
