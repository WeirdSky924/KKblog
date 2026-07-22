import re
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from django.db import IntegrityError, transaction

from apps.notifications.models import Notification, NotificationReceipt

_KEY = re.compile(r"[a-z][a-z0-9_.-]{2,95}\Z")
_TARGET = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_FORBIDDEN = {
    "authorization",
    "body",
    "cookie",
    "email",
    "html",
    "ip",
    "password",
    "path",
    "raw",
    "reporter",
    "secret",
    "token",
    "url",
}


class NotificationRejected(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NotificationTemplateSchema:
    key: str
    target_type: str
    allowed_payload_fields: frozenset[str]

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.key) or not _KEY.fullmatch(self.target_type):
            raise NotificationRejected("Invalid notification schema")
        for field in self.allowed_payload_fields:
            lowered = field.casefold()
            if not _KEY.fullmatch(field) or set(lowered.split("_")) & _FORBIDDEN:
                raise NotificationRejected("Unsafe notification field")


_TEMPLATES: dict[str, NotificationTemplateSchema] = {}


def register_notification_template(
    schema: NotificationTemplateSchema, *, replace: bool = False
) -> None:
    current = _TEMPLATES.get(schema.key)
    if current is not None and current != schema and not replace:
        raise NotificationRejected("Notification template already registered")
    _TEMPLATES[schema.key] = schema


def registered_notification_templates() -> MappingProxyType:
    return MappingProxyType(_TEMPLATES)


def _safe_value(value):
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, str):
        if (
            len(value) > 200
            or "\x00" in value
            or "<" in value
            or ">" in value
            or "://" in value
        ):
            raise NotificationRejected("Unsafe notification value")
        return value
    if isinstance(value, list | tuple) and len(value) <= 20:
        return [_safe_value(item) for item in value]
    raise NotificationRejected("Unsafe notification value")


def _existing_matches(
    notification: Notification,
    *,
    schema: NotificationTemplateSchema,
    target_id: str,
    payload: dict[str, object],
) -> Notification:
    if (
        notification.template_key != schema.key
        or notification.target_type != schema.target_type
        or notification.target_id != target_id
        or notification.payload_safe != payload
    ):
        raise NotificationRejected("Dedupe key targets different notification")
    return notification


def deliver_notification(
    *,
    template_key: str,
    recipient_ids,
    target_id: str,
    payload: dict[str, object],
    actor_id=None,
    dedupe_key: str | None = None,
) -> Notification:
    schema = _TEMPLATES.get(template_key)
    if schema is None:
        raise NotificationRejected("Unknown notification template")
    if not _TARGET.fullmatch(target_id):
        raise NotificationRejected("Invalid notification target")
    if (
        not isinstance(payload, dict)
        or not set(payload) <= schema.allowed_payload_fields
    ):
        raise NotificationRejected("Unknown notification payload field")
    safe_payload = {key: _safe_value(value) for key, value in payload.items()}
    try:
        recipients = tuple(dict.fromkeys(UUID(str(value)) for value in recipient_ids))
        actor = UUID(str(actor_id)) if actor_id is not None else None
    except (TypeError, ValueError):
        raise NotificationRejected("Invalid notification identity") from None
    if not recipients:
        raise NotificationRejected("Notification requires recipients")
    if dedupe_key is not None and (
        len(dedupe_key) > 255 or not _TARGET.fullmatch(dedupe_key)
    ):
        raise NotificationRejected("Invalid notification dedupe key")
    if dedupe_key:
        existing = Notification.objects.filter(dedupe_key=dedupe_key).first()
        if existing:
            return _existing_matches(
                existing, schema=schema, target_id=target_id, payload=safe_payload
            )
    try:
        with transaction.atomic():
            notification = Notification.objects.create(
                template_key=schema.key,
                actor_id=actor,
                target_type=schema.target_type,
                target_id=target_id,
                payload_safe=safe_payload,
                dedupe_key=dedupe_key,
            )
            NotificationReceipt.objects.bulk_create(
                [
                    NotificationReceipt(
                        notification=notification, recipient_id=recipient_id
                    )
                    for recipient_id in recipients
                ]
            )
            return notification
    except IntegrityError:
        if not dedupe_key:
            raise
        existing = Notification.objects.get(dedupe_key=dedupe_key)
        return _existing_matches(
            existing, schema=schema, target_id=target_id, payload=safe_payload
        )
