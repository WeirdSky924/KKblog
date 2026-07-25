from uuid import UUID

from django.db import transaction
from django.db.models import Q

from apps.core.events import EventEnvelope, consume_once, enqueue_event
from apps.core.ids import is_ulid
from apps.core.time.clock import Clock, SystemClock

from ..events import REPORT_CLOSED
from ..models import (
    ArticleAppeal,
    ArticleModerationCase,
    DeletedAccountIdentity,
    Report,
    ReportAppeal,
    ReportRecoverySnapshot,
)

CONSUMER_NAME = "moderation.account-deleted.v1"
EVENT_TYPE = "account.deleted.v1"
UNRESOLVED_REPORT_STATES = (
    Report.State.PENDING,
    Report.State.UPHELD,
    Report.State.REJECTED,
    Report.State.APPEAL_PENDING,
)
UNRESOLVED_CASE_STATES = (
    ArticleModerationCase.State.ACTIVE,
    ArticleModerationCase.State.APPEALED,
)


class ModerationAccountDeletionEventError(ValueError):
    pass


def _event_identity(envelope: EventEnvelope) -> tuple[UUID, str]:
    expected = {
        "deletion_id",
        "was_author",
        "author_disposition",
        "disposition_id",
        "article_count",
    }
    if (
        not isinstance(envelope, EventEnvelope)
        or envelope.event_type != EVENT_TYPE
        or envelope.schema_version != 1
        or envelope.aggregate_type != "account"
        or envelope.actor_id is None
        or set(envelope.payload) != expected
        or not isinstance(envelope.payload["deletion_id"], str)
        or not is_ulid(envelope.payload["deletion_id"])
        or not isinstance(envelope.payload["was_author"], bool)
        or envelope.payload["author_disposition"]
        not in {"no_articles", "delete_all", "export_then_delete"}
        or not isinstance(envelope.payload["disposition_id"], str)
        or not is_ulid(envelope.payload["disposition_id"])
        or isinstance(envelope.payload["article_count"], bool)
        or not isinstance(envelope.payload["article_count"], int)
        or not 0 <= envelope.payload["article_count"] <= 1_000_000
    ):
        raise ModerationAccountDeletionEventError(
            "Invalid moderation account deletion event"
        )
    try:
        account_id = UUID(envelope.aggregate_id)
    except (TypeError, ValueError):
        raise ModerationAccountDeletionEventError(
            "Invalid moderation account deletion event"
        ) from None
    return account_id, envelope.payload["deletion_id"]


def _close_reports(
    envelope: EventEnvelope,
    *,
    account_id: UUID,
    deletion_id: str,
    clock: Clock,
) -> None:
    reports = list(
        Report.objects.select_for_update()
        .filter(state__in=UNRESOLVED_REPORT_STATES)
        .filter(Q(reporter_id=account_id) | Q(reported_author_id=account_id))
        .order_by("id")
    )
    for report in reports:
        reporter_deleted = report.reporter_id == account_id
        reason = (
            Report.ClosureReason.REPORTER_DELETED
            if reporter_deleted
            else Report.ClosureReason.REPORTED_ACCOUNT_DELETED
        )
        report.state = Report.State.CLOSED
        report.closure_reason = reason
        report.closure_deletion_id = deletion_id
        report.closed_at = envelope.occurred_at
        report.save(
            update_fields=(
                "state",
                "closure_reason",
                "closure_deletion_id",
                "closed_at",
                "updated_at",
            )
        )
        ReportAppeal.objects.select_for_update().filter(
            report=report,
            state=ReportAppeal.State.PENDING,
        ).update(state=ReportAppeal.State.CLOSED)
        ReportRecoverySnapshot.objects.select_for_update().filter(
            report=report
        ).delete()
        if not reporter_deleted:
            enqueue_event(
                REPORT_CLOSED,
                aggregate_type="report",
                aggregate_id=report.id,
                actor_id=envelope.actor_id,
                trace_code=envelope.trace_code,
                payload={
                    "target_comment_id": report.target_comment_id,
                    "outcome": "CONTENT_DELETED",
                    "recipient_id": str(report.reporter_id),
                },
                clock=clock,
            )


def _close_article_cases(
    envelope: EventEnvelope,
    *,
    account_id: UUID,
    deletion_id: str,
) -> None:
    cases = list(
        ArticleModerationCase.objects.select_for_update()
        .filter(author_id=account_id, state__in=UNRESOLVED_CASE_STATES)
        .order_by("id")
    )
    for case in cases:
        case.state = ArticleModerationCase.State.CLOSED
        case.resolved_by_id = envelope.actor_id
        case.resolved_at = envelope.occurred_at
        case.closure_reason = ArticleModerationCase.ClosureReason.ACCOUNT_DELETED
        case.closure_deletion_id = deletion_id
        case.save(
            update_fields=(
                "state",
                "resolved_by_id",
                "resolved_at",
                "closure_reason",
                "closure_deletion_id",
                "updated_at",
            )
        )
        ArticleAppeal.objects.select_for_update().filter(
            case=case,
            state=ArticleAppeal.State.PENDING,
        ).update(state=ArticleAppeal.State.CLOSED)


def _apply(envelope: EventEnvelope, *, clock: Clock) -> None:
    account_id, deletion_id = _event_identity(envelope)
    with transaction.atomic():
        identity, created = (
            DeletedAccountIdentity.objects.select_for_update().get_or_create(
                account_id=account_id,
                defaults={
                    "deletion_id": deletion_id,
                    "deleted_at": envelope.occurred_at,
                },
            )
        )
        if not created and identity.deletion_id != deletion_id:
            raise ModerationAccountDeletionEventError(
                "Deleted account identity conflict"
            )
        _close_reports(
            envelope,
            account_id=account_id,
            deletion_id=deletion_id,
            clock=clock,
        )
        _close_article_cases(
            envelope,
            account_id=account_id,
            deletion_id=deletion_id,
        )


def consume_account_deleted(
    envelope: EventEnvelope,
    *,
    lease_seconds: int = 60,
    retry_delay_seconds: int = 60,
    clock: Clock | None = None,
):
    active_clock = clock or SystemClock()
    _event_identity(envelope)
    return consume_once(
        envelope,
        CONSUMER_NAME,
        lambda item: _apply(item, clock=active_clock),
        lease_seconds=lease_seconds,
        retry_delay_seconds=retry_delay_seconds,
        clock=active_clock,
    )
