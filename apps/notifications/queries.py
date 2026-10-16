from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode
from uuid import UUID

from django.core import signing
from django.core.paginator import Paginator
from django.db.models import Count, IntegerField, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

from apps.core.ids import normalize_ulid
from apps.core.pagination import PageSlice, page_window
from apps.notifications.models import Notification, NotificationReceipt
from apps.notifications.services.broadcast import BROADCAST_TEMPLATE_KEYS
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
    message_html: str
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
    unread_count: int = 0


@dataclass(frozen=True, slots=True)
class BroadcastSummary:
    notification_id: str
    headline: str
    message: str
    message_html: str
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
    message_html: str
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

    @property
    def page_number(self) -> int:
        return self.recipient_page

    @property
    def total_pages(self) -> int:
        return self.recipient_pages

    @property
    def has_previous(self) -> bool:
        return self.recipient_page > 1

    @property
    def has_next(self) -> bool:
        return self.recipient_page < self.recipient_pages

    @property
    def page_window(self) -> tuple[int | None, ...]:
        return page_window(self.recipient_page, self.recipient_pages)


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
    return Notification.objects.filter(
        template_key__in=BROADCAST_TEMPLATE_KEYS
    ).annotate(
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
        message_html=rendered.message_html,
        state=_broadcast_state(notification),
        recipient_count=recipient_count,
        read_count=read_count,
        unread_count=recipient_count - read_count,
        created_at=notification.created_at,
    )


def broadcast_list(
    *,
    is_admin: bool,
    limit: int = 50,
    page: int | None = None,
    page_size: int = 20,
) -> tuple[BroadcastSummary, ...] | PageSlice[BroadcastSummary]:
    _require_broadcast_admin(is_admin)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200:
        raise ValueError("Invalid broadcast list limit")
    if page is not None and (
        isinstance(page, bool) or page < 1 or page_size not in (10, 20, 50)
    ):
        raise ValueError("Invalid broadcast page")
    ordered = _broadcast_query().order_by("-created_at", "-id")
    if page is None:
        return tuple(
            _broadcast_summary(notification) for notification in ordered[:limit]
        )
    paginator = Paginator(ordered, page_size)
    selected = paginator.get_page(page)
    return PageSlice(
        items=tuple(
            _broadcast_summary(notification) for notification in selected.object_list
        ),
        page_number=selected.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
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
        message_html=summary.message_html,
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


def _unread_count_expression(recipient_id: UUID):
    unread = (
        NotificationReceipt.objects.filter(
            recipient_id=recipient_id,
            read_at__isnull=True,
            notification__hidden_at__isnull=True,
            notification__deleted_at__isnull=True,
        )
        .order_by()
        .values("recipient_id")
        .annotate(total=Count("id"))
        .values("total")[:1]
    )
    return Coalesce(
        Subquery(unread, output_field=IntegerField()),
        Value(0, output_field=IntegerField()),
    )


def _target_url(target_type: str, target_id: str) -> str | None:
    if target_type == "article":
        return reverse("article:detail", kwargs={"article_id": target_id})
    if target_type == "tag":
        return reverse("public:tag", kwargs={"tag_id": target_id})
    if target_type == "account_role":
        return reverse("accounts:settings")
    if target_type == "admin_user":
        return f"{reverse('admin:users')}?{urlencode({'q': target_id})}"
    if target_type in {"knowledge_document", "learning_appeal"}:
        return reverse("learning:documents")
    if target_type == "question_bank":
        return reverse("question_banks:detail", kwargs={"bank_id": target_id})
    if target_type == "question_bank_series":
        return reverse("learning:documents")
    return None


def _item(receipt: NotificationReceipt) -> NotificationItem:
    notification = receipt.notification
    rendered = render_notification(notification.template_key, notification.payload_safe)
    return NotificationItem(
        notification_id=notification.id,
        title=rendered.title,
        message=rendered.message,
        message_html=rendered.message_html,
        target_url=_target_url(notification.target_type, notification.target_id),
        is_read=receipt.read_at is not None,
        created_at=notification.created_at,
    )


def unread_notification_count(*, recipient_id: UUID | str) -> int:
    identity = _recipient_id(recipient_id)
    return _visible_receipts(identity).filter(read_at__isnull=True).count()


def unread_target_notification_count(
    *, recipient_id: UUID | str, target_type: str
) -> int:
    identity = _recipient_id(recipient_id)
    if (
        not isinstance(target_type, str)
        or not target_type
        or len(target_type) > 64
        or not target_type.replace("_", "").isalnum()
    ):
        raise ValueError("Invalid notification target type")
    return (
        _visible_receipts(identity)
        .filter(
            read_at__isnull=True,
            notification__target_type=target_type,
        )
        .count()
    )


def notification_popover(
    *, recipient_id: UUID | str, limit: int = 5
) -> NotificationPopover:
    identity = _recipient_id(recipient_id)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 5:
        raise ValueError("Invalid notification popover limit")
    rows = tuple(
        _visible_receipts(identity)
        .annotate(unread_count_value=_unread_count_expression(identity))
        .order_by("-notification__created_at", "-notification_id")[:limit]
    )
    return NotificationPopover(
        items=tuple(_item(row) for row in rows),
        unread_count=(int(rows[0].unread_count_value) if rows else 0),
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
    query = query.annotate(unread_count_value=_unread_count_expression(identity))
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
        unread_count=int(fetched[0].unread_count_value) if fetched else 0,
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
