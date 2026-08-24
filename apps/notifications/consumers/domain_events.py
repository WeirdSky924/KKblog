import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from apps.core.events import EventEnvelope, consume_once
from apps.core.ids import is_ulid
from apps.core.time.clock import Clock
from apps.notifications.models import NotificationReceipt
from apps.notifications.services.delivery import (
    NotificationRejected,
    deliver_notification,
)
from apps.notifications.services.recipients import (
    existing_notification_recipient_ids,
)

CONSUMER_NAME = "notifications.domain-events.v1"
_REPORT_REASONS = frozenset(
    {"SPAM", "HARASSMENT", "ILLEGAL_DANGEROUS", "PRIVACY", "IRRELEVANT", "OTHER"}
)


@dataclass(frozen=True, slots=True)
class _Delivery:
    template_key: str
    recipient_ids: tuple[UUID, ...]
    target_id: str
    payload: dict[str, object]
    dedupe_key: str


def _reject_unless(condition: bool) -> None:
    if not condition:
        raise NotificationRejected("Invalid domain notification event")


def _uuid(value: object) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise NotificationRejected("Invalid domain notification identity") from None


def _recipients(value: object, *, maximum: int = 2) -> tuple[UUID, ...]:
    _reject_unless(isinstance(value, list) and len(value) <= maximum)
    return tuple(dict.fromkeys(_uuid(item) for item in value))


def _ulid(value: object) -> str:
    _reject_unless(isinstance(value, str) and is_ulid(value))
    return value


def _date(value: object) -> str:
    try:
        parsed = date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    _reject_unless(parsed is not None and parsed.isoformat() == value)
    return value


def _report_context(payload: Mapping[str, object]) -> None:
    reason = payload["reason"]
    description = payload["description"]
    _reject_unless(
        isinstance(reason, str)
        and reason in _REPORT_REASONS
        and isinstance(description, str)
        and len(description) <= 200
        and "<" not in description
        and ">" not in description
        and "://" not in description
        and all(
            character.isprintable() or character in "\n\t" for character in description
        )
    )


def _base(
    envelope: EventEnvelope,
    *,
    event_type: str,
    aggregate_type: str,
    fields: frozenset[str],
    schema_version: int = 1,
) -> Mapping[str, object]:
    _reject_unless(
        isinstance(envelope, EventEnvelope)
        and envelope.event_type == event_type
        and envelope.schema_version == schema_version
        and envelope.aggregate_type == aggregate_type
        and set(envelope.payload) == fields
    )
    return envelope.payload


def _delivery(
    envelope: EventEnvelope,
    *,
    recipients: tuple[UUID, ...],
    payload: dict[str, object],
    dedupe_key: str | None = None,
    target_id: str | None = None,
) -> _Delivery:
    return _Delivery(
        template_key=envelope.event_type,
        recipient_ids=recipients,
        target_id=target_id or envelope.aggregate_id,
        payload=payload,
        dedupe_key=dedupe_key or f"event:{envelope.event_id}",
    )


def _tag_reviewed(envelope: EventEnvelope) -> _Delivery:
    payload = _base(
        envelope,
        event_type="tag.reviewed.v1",
        aggregate_type="tag",
        fields=frozenset({"outcome", "recipient_id"}),
    )
    _uuid(envelope.aggregate_id)
    _reject_unless(payload["outcome"] in {"approved", "rejected"})
    return _delivery(
        envelope,
        recipients=(_uuid(payload["recipient_id"]),),
        payload={"outcome": payload["outcome"]},
    )


def _tag_restore_conflict(envelope: EventEnvelope) -> _Delivery:
    payload = _base(
        envelope,
        event_type="tag.restore_conflict.v1",
        aggregate_type="tag",
        fields=frozenset({"article_id", "recipient_id"}),
    )
    _uuid(envelope.aggregate_id)
    article_id = _ulid(payload["article_id"])
    return _delivery(
        envelope,
        recipients=(_uuid(payload["recipient_id"]),),
        payload={"article_id": article_id},
    )


def _article_admin_viewed(envelope: EventEnvelope) -> _Delivery:
    payload = _base(
        envelope,
        event_type="article.admin_viewed.v1",
        aggregate_type="article",
        fields=frozenset({"recipient_id", "view_date"}),
    )
    article_id = _ulid(envelope.aggregate_id)
    recipient = _uuid(payload["recipient_id"])
    view_date = _date(payload["view_date"])
    return _delivery(
        envelope,
        recipients=(recipient,),
        payload={"view_date": view_date},
        dedupe_key=f"article-view:{recipient}:{article_id}:{view_date}",
    )


def _comment_deep_thread(envelope: EventEnvelope) -> _Delivery:
    fields = frozenset(
        {"thread_id", "target_type", "target_id", "owner_id", "root_id", "depth"}
    )
    payload = _base(
        envelope,
        event_type="comment.deep_thread.v1",
        aggregate_type="discussion_thread",
        fields=fields,
    )
    thread_id = _uuid(envelope.aggregate_id)
    _reject_unless(_uuid(payload["thread_id"]) == thread_id)
    _ulid(payload["root_id"])
    depth = payload["depth"]
    _reject_unless(
        not isinstance(depth, bool) and isinstance(depth, int) and depth > 100
    )
    return _delivery(
        envelope,
        recipients=(_uuid(payload["owner_id"]),),
        payload={"depth": depth},
    )


def _comment_deleted(envelope: EventEnvelope) -> _Delivery | None:
    fields = frozenset(
        {
            "thread_id",
            "target_type",
            "target_id",
            "comment_id",
            "deleted_by_kind",
            "recipient_ids",
            "reason",
        }
    )
    payload = _base(
        envelope,
        event_type="comment.deleted.v1",
        aggregate_type="comment",
        fields=fields,
    )
    comment_id = _ulid(envelope.aggregate_id)
    _reject_unless(_ulid(payload["comment_id"]) == comment_id)
    recipients = _recipients(payload["recipient_ids"])
    deleted_by_kind = payload["deleted_by_kind"]
    _reject_unless(deleted_by_kind in {"SELF", "OWNER", "ADMIN"})
    if deleted_by_kind != "ADMIN":
        _reject_unless(not recipients and payload["reason"] is None)
        return None
    return _delivery(
        envelope,
        recipients=recipients,
        payload={
            "deleted_by_kind": deleted_by_kind,
            "reason": payload["reason"],
        },
    )


def _report_reviewed(envelope: EventEnvelope) -> _Delivery:
    fields = frozenset(
        {"target_comment_id", "outcome", "decision_reason", "recipient_ids"}
    )
    payload = _base(
        envelope,
        event_type="report.reviewed.v1",
        aggregate_type="report",
        fields=fields,
    )
    _ulid(envelope.aggregate_id)
    _ulid(payload["target_comment_id"])
    recipients = _recipients(payload["recipient_ids"])
    _reject_unless(bool(recipients))
    return _delivery(
        envelope,
        recipients=recipients,
        payload={
            "outcome": payload["outcome"],
            "decision_reason": payload["decision_reason"],
        },
    )


def _report_reviewed_v2(envelope: EventEnvelope) -> _Delivery:
    fields = frozenset(
        {
            "target_comment_id",
            "reason",
            "description",
            "outcome",
            "decision_reason",
            "recipient_ids",
        }
    )
    payload = _base(
        envelope,
        event_type="report.reviewed.v2",
        aggregate_type="report",
        fields=fields,
        schema_version=2,
    )
    report_id = _ulid(envelope.aggregate_id)
    target_comment_id = _ulid(payload["target_comment_id"])
    _report_context(payload)
    recipients = _recipients(payload["recipient_ids"])
    _reject_unless(bool(recipients))
    return _delivery(
        envelope,
        recipients=recipients,
        payload={
            "report_id": report_id,
            "target_comment_id": target_comment_id,
            "reason": payload["reason"],
            "description": payload["description"],
            "outcome": payload["outcome"],
            "decision_reason": payload["decision_reason"],
        },
    )


def _report_finalized(envelope: EventEnvelope) -> _Delivery:
    fields = frozenset(
        {
            "target_comment_id",
            "outcome",
            "decision_reason",
            "recipient_ids",
            "recovery_status",
        }
    )
    payload = _base(
        envelope,
        event_type="report.finalized.v1",
        aggregate_type="report",
        fields=fields,
    )
    _ulid(envelope.aggregate_id)
    _ulid(payload["target_comment_id"])
    recipients = _recipients(payload["recipient_ids"])
    _reject_unless(bool(recipients))
    return _delivery(
        envelope,
        recipients=recipients,
        payload={
            "outcome": payload["outcome"],
            "decision_reason": payload["decision_reason"],
            "recovery_status": payload["recovery_status"],
        },
    )


def _report_finalized_v2(envelope: EventEnvelope) -> _Delivery:
    fields = frozenset(
        {
            "target_comment_id",
            "reason",
            "description",
            "outcome",
            "basis_outcome",
            "decision_reason",
            "recipient_ids",
            "recovery_status",
        }
    )
    payload = _base(
        envelope,
        event_type="report.finalized.v2",
        aggregate_type="report",
        fields=fields,
        schema_version=2,
    )
    report_id = _ulid(envelope.aggregate_id)
    target_comment_id = _ulid(payload["target_comment_id"])
    _report_context(payload)
    recipients = _recipients(payload["recipient_ids"])
    _reject_unless(bool(recipients))
    return _delivery(
        envelope,
        recipients=recipients,
        payload={
            "report_id": report_id,
            "target_comment_id": target_comment_id,
            "reason": payload["reason"],
            "description": payload["description"],
            "basis_outcome": payload["basis_outcome"],
            "outcome": payload["outcome"],
            "decision_reason": payload["decision_reason"],
            "recovery_status": payload["recovery_status"],
        },
    )


def _report_closed(envelope: EventEnvelope) -> _Delivery:
    fields = frozenset({"target_comment_id", "outcome", "recipient_id"})
    payload = _base(
        envelope,
        event_type="report.closed.v1",
        aggregate_type="report",
        fields=fields,
    )
    _ulid(envelope.aggregate_id)
    _ulid(payload["target_comment_id"])
    return _delivery(
        envelope,
        recipients=(_uuid(payload["recipient_id"]),),
        payload={"outcome": payload["outcome"]},
    )


def _article_event(envelope: EventEnvelope) -> _Delivery:
    definitions = {
        "article.moderated.v1": (
            frozenset({"case_id", "action", "reason", "recipient_id"}),
            ("action", "reason"),
        ),
        "article.moderation_restored.v1": (
            frozenset({"case_id", "action", "recipient_id", "recovery_status"}),
            ("action", "recovery_status"),
        ),
        "article.moderation_finalized.v1": (
            frozenset(
                {
                    "case_id",
                    "action",
                    "outcome",
                    "decision_reason",
                    "recipient_id",
                    "recovery_status",
                }
            ),
            ("action", "outcome", "decision_reason", "recovery_status"),
        ),
    }
    try:
        fields, delivered_fields = definitions[envelope.event_type]
    except KeyError:
        raise NotificationRejected("Unsupported domain notification event") from None
    payload = _base(
        envelope,
        event_type=envelope.event_type,
        aggregate_type="article",
        fields=fields,
    )
    _ulid(envelope.aggregate_id)
    _ulid(payload["case_id"])
    return _delivery(
        envelope,
        recipients=(_uuid(payload["recipient_id"]),),
        payload={field: payload[field] for field in delivered_fields},
    )


def _exchange_import_title_warning(envelope: EventEnvelope) -> _Delivery:
    payload = _base(
        envelope,
        event_type="exchange.import_title_warning.v1",
        aggregate_type="article",
        fields=frozenset({"job_id", "item_id", "recipient_id"}),
    )
    _ulid(envelope.aggregate_id)
    _ulid(payload["job_id"])
    item_id = _ulid(payload["item_id"])
    return _delivery(
        envelope,
        recipients=(_uuid(payload["recipient_id"]),),
        payload={},
        dedupe_key=f"exchange-import-title-warning:{item_id}",
    )


def _exchange_export_completed(envelope: EventEnvelope) -> _Delivery:
    payload = _base(
        envelope,
        event_type="exchange.export_completed.v1",
        aggregate_type="export_job",
        fields=frozenset({"recipient_id"}),
    )
    job_id = _ulid(envelope.aggregate_id)
    return _delivery(
        envelope,
        recipients=(_uuid(payload["recipient_id"]),),
        payload={},
        dedupe_key=f"exchange-export-completed:{job_id}",
    )


def _exchange_export_author_content(envelope: EventEnvelope) -> _Delivery:
    payload = _base(
        envelope,
        event_type="exchange.export_author_content.v1",
        aggregate_type="export_job",
        fields=frozenset({"recipient_id", "export_date"}),
    )
    _ulid(envelope.aggregate_id)
    recipient = _uuid(payload["recipient_id"])
    export_date = _date(payload["export_date"])
    return _delivery(
        envelope,
        recipients=(recipient,),
        payload={},
        dedupe_key=f"exchange-export-author:{recipient}:{export_date}",
        target_id=str(recipient),
    )


def _learning_review(envelope: EventEnvelope) -> _Delivery:
    payload = _base(
        envelope,
        event_type=envelope.event_type,
        aggregate_type="knowledge_document",
        fields=frozenset({"recipient_id"}),
    )
    document_id = _uuid(envelope.aggregate_id)
    return _delivery(
        envelope,
        recipients=(_uuid(payload["recipient_id"]),),
        payload={},
        dedupe_key=f"{envelope.event_type}:{document_id}",
        target_id=str(document_id),
    )


def _learning_generation(envelope: EventEnvelope) -> _Delivery:
    fields = frozenset({"recipient_id"})
    if envelope.event_type == "learning.generation_failed.v1":
        if set(envelope.payload) == {"recipient_id", "error_code"}:
            fields = frozenset({"recipient_id", "error_code"})
        elif set(envelope.payload) != {"recipient_id"}:
            raise NotificationRejected("Invalid learning generation failure payload")
    payload = _base(
        envelope,
        event_type=envelope.event_type,
        aggregate_type="question_bank_series",
        fields=fields,
    )
    series_id = _uuid(envelope.aggregate_id)
    delivery_payload = {}
    if (
        envelope.event_type == "learning.generation_failed.v1"
        and "error_code" in payload
    ):
        error_code = payload["error_code"]
        _reject_unless(
            isinstance(error_code, str)
            and len(error_code) <= 96
            and re.fullmatch(
                r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*",
                error_code,
            )
            is not None
        )
        delivery_payload = {"error_code": error_code}
    return _delivery(
        envelope,
        recipients=(_uuid(payload["recipient_id"]),),
        payload=delivery_payload,
        dedupe_key=f"{envelope.event_type}:{series_id}",
        target_id=str(series_id),
    )


def _learning_appeal(envelope: EventEnvelope) -> _Delivery:
    payload = _base(
        envelope,
        event_type=envelope.event_type,
        aggregate_type="learning_appeal",
        fields=frozenset({"recipient_id"}),
    )
    appeal_id = _uuid(envelope.aggregate_id)
    return _delivery(
        envelope,
        recipients=(_uuid(payload["recipient_id"]),),
        payload={},
        dedupe_key=f"{envelope.event_type}:{appeal_id}",
        target_id=str(appeal_id),
    )


def _learning_administration(envelope: EventEnvelope) -> _Delivery:
    aggregate_type = envelope.aggregate_type
    if aggregate_type == "knowledge_document":
        expected_type = "knowledge_document"
    elif aggregate_type == "question_bank":
        expected_type = "question_bank"
    else:
        raise NotificationRejected("Unsupported learning administration target")
    payload = _base(
        envelope,
        event_type=envelope.event_type,
        aggregate_type=expected_type,
        fields=frozenset({"recipient_id", "action"}),
    )
    action = payload["action"]
    _reject_unless(action in {"HIDE", "RESTORE", "DELETE"})
    return _delivery(
        envelope,
        recipients=(_uuid(payload["recipient_id"]),),
        payload={"action": action},
    )


_BUILDERS: dict[str, Callable[[EventEnvelope], _Delivery | None]] = {
    "tag.reviewed.v1": _tag_reviewed,
    "tag.restore_conflict.v1": _tag_restore_conflict,
    "article.admin_viewed.v1": _article_admin_viewed,
    "comment.deep_thread.v1": _comment_deep_thread,
    "comment.deleted.v1": _comment_deleted,
    "report.reviewed.v1": _report_reviewed,
    "report.reviewed.v2": _report_reviewed_v2,
    "report.finalized.v1": _report_finalized,
    "report.finalized.v2": _report_finalized_v2,
    "report.closed.v1": _report_closed,
    "article.moderated.v1": _article_event,
    "article.moderation_restored.v1": _article_event,
    "article.moderation_finalized.v1": _article_event,
    "exchange.import_title_warning.v1": _exchange_import_title_warning,
    "exchange.export_completed.v1": _exchange_export_completed,
    "exchange.export_author_content.v1": _exchange_export_author_content,
    "learning.review_approved.v1": _learning_review,
    "learning.review_rejected.v1": _learning_review,
    "learning.review_failed.v1": _learning_review,
    "learning.generation_completed.v1": _learning_generation,
    "learning.generation_partial.v1": _learning_generation,
    "learning.generation_failed.v1": _learning_generation,
    "learning.appeal_approved.v1": _learning_appeal,
    "learning.appeal_rejected.v1": _learning_appeal,
    "learning.document_administration_changed.v1": _learning_administration,
    "learning.question_bank_administration_changed.v1": _learning_administration,
}


def _deliver(envelope: EventEnvelope) -> None:
    try:
        delivery = _BUILDERS[envelope.event_type](envelope)
    except KeyError:
        raise NotificationRejected("Unsupported domain notification event") from None
    if delivery is None:
        return
    recipients = existing_notification_recipient_ids(delivery.recipient_ids)
    if not recipients:
        return
    notification = deliver_notification(
        template_key=delivery.template_key,
        recipient_ids=recipients,
        target_id=delivery.target_id,
        payload=delivery.payload,
        actor_id=envelope.actor_id,
        dedupe_key=delivery.dedupe_key,
    )
    receipt_ids = set(
        NotificationReceipt.objects.filter(notification=notification).values_list(
            "recipient_id", flat=True
        )
    )
    if receipt_ids != set(recipients):
        raise NotificationRejected("Notification receipt set is incomplete")


def consume_domain_notification(
    envelope: EventEnvelope,
    *,
    lease_seconds: int = 60,
    retry_delay_seconds: int = 60,
    clock: Clock | None = None,
):
    return consume_once(
        envelope,
        CONSUMER_NAME,
        _deliver,
        lease_seconds=lease_seconds,
        retry_delay_seconds=retry_delay_seconds,
        clock=clock,
    )
