from dataclasses import dataclass
from enum import StrEnum
from ipaddress import IPv6Address, ip_address
from uuid import UUID

from django.db import transaction

from apps.comments.public import CommentDeletionError, delete_comment_for_report
from apps.core.events import enqueue_event
from apps.core.ids import normalize_ulid
from apps.core.time.clock import Clock, SystemClock, require_aware
from apps.operations.public import record_audit_entry

from ..events import REPORT_REVIEWED_V2, report_notification_description
from ..models import Report, ReportRecoverySnapshot
from ..ports import ModerationAccountPolicy, default_moderation_account_policy


class ReportReviewError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


class ReportReviewOutcome(StrEnum):
    UPHELD = "UPHELD"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class ReportReviewResult:
    report_id: str
    state: str
    comment_changed: bool
    snapshot_created: bool
    image_count: int
    recipient_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ReportRecoverySnapshotAccess:
    exists: bool
    can_read: bool


def _actor(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ReportReviewError(
            "moderation.review_forbidden.v1",
            "当前身份不能裁决举报。",
        ) from None


def _report_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ReportReviewError(
            "moderation.report_unavailable.v1",
            "当前举报不可用。",
        ) from None


def _client_ip(value: str) -> str:
    try:
        parsed = ip_address(value)
    except (TypeError, ValueError):
        raise ReportReviewError(
            "moderation.network_invalid.v1",
            "当前网络信息无效。",
        ) from None
    if isinstance(parsed, IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    return str(parsed)


def _outcome(value) -> ReportReviewOutcome:
    try:
        return ReportReviewOutcome(value)
    except (TypeError, ValueError):
        raise ReportReviewError(
            "moderation.review_outcome_invalid.v1",
            "请选择有效的裁决结果。",
        ) from None


def _decision_reason(value) -> str:
    if not isinstance(value, str):
        raise ReportReviewError(
            "moderation.decision_reason_invalid.v1",
            "裁决说明需为 200 个字符以内的纯文本。",
        )
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if (
        len(normalized) > 200
        or "<" in normalized
        or ">" in normalized
        or "://" in normalized
        or any(
            not character.isprintable() and character not in "\n\t"
            for character in normalized
        )
    ):
        raise ReportReviewError(
            "moderation.decision_reason_invalid.v1",
            "裁决说明需为 200 个字符以内的纯文本。",
        )
    return normalized


def _authorize(
    *,
    actor_id,
    client_ip: str,
    account_policy: ModerationAccountPolicy,
) -> tuple[UUID, str]:
    actor = _actor(actor_id)
    address = _client_ip(client_ip)
    if not account_policy.is_active_account(actor):
        raise ReportReviewError(
            "moderation.account_unavailable.v1",
            "当前账户无法裁决举报。",
        )
    if account_policy.is_ip_blocked(address):
        raise ReportReviewError(
            "moderation.network_restricted.v1",
            "当前网络暂时受限。",
        )
    if not account_policy.is_administrator(actor):
        raise ReportReviewError(
            "moderation.review_forbidden.v1",
            "当前身份不能裁决举报。",
        )
    return actor, address


def _recipients(report: Report, outcome: ReportReviewOutcome) -> tuple[UUID, ...]:
    candidates = [report.reporter_id]
    if outcome == ReportReviewOutcome.UPHELD:
        candidates.append(report.reported_author_id)
    return tuple(dict.fromkeys(value for value in candidates if value is not None))


def review_report(
    *,
    actor_id,
    report_id: str,
    outcome,
    decision_reason: str,
    client_ip: str,
    trace_code: str,
    account_policy: ModerationAccountPolicy | None = None,
    clock: Clock | None = None,
) -> ReportReviewResult:
    accounts = account_policy or default_moderation_account_policy()
    actor, address = _authorize(
        actor_id=actor_id,
        client_ip=client_ip,
        account_policy=accounts,
    )
    identity = _report_id(report_id)
    normalized_outcome = _outcome(outcome)
    normalized_reason = _decision_reason(decision_reason)
    active_clock = clock or SystemClock()
    reviewed_at = require_aware(active_clock.now())

    with transaction.atomic():
        report = Report.objects.select_for_update().filter(pk=identity).first()
        if report is None:
            raise ReportReviewError(
                "moderation.report_unavailable.v1",
                "当前举报不可用。",
            )
        if report.state != Report.State.PENDING:
            raise ReportReviewError(
                "moderation.report_state_conflict.v1",
                "该举报已经完成初审。",
            )

        deletion = None
        snapshot_created = False
        if normalized_outcome == ReportReviewOutcome.UPHELD:
            try:
                deletion = delete_comment_for_report(
                    comment_id=report.target_comment_id,
                    actor_id=actor,
                    client_ip=address,
                    account_policy=accounts,
                )
            except CommentDeletionError:
                raise ReportReviewError(
                    "moderation.report_target_unavailable.v1",
                    "被举报评论当前无法完成裁决。",
                ) from None
            if deletion.changed:
                ReportRecoverySnapshot.objects.create(
                    report=report,
                    comment_id=deletion.comment_id,
                    body=deletion.body,
                    previous_state=deletion.previous_state,
                    previous_visible_at=deletion.previous_visible_at,
                    image_count=len(deletion.asset_ids),
                )
                snapshot_created = True

        report.state = normalized_outcome.value
        report.reviewed_by_id = actor
        report.reviewed_at = reviewed_at
        report.decision_reason = normalized_reason
        report.save(
            update_fields=(
                "state",
                "reviewed_by_id",
                "reviewed_at",
                "decision_reason",
                "updated_at",
            )
        )
        changed = bool(deletion and deletion.changed)
        image_count = len(deletion.asset_ids) if deletion else 0
        recipients = _recipients(report, normalized_outcome)
        record_audit_entry(
            action="moderation.report.review",
            actor_id=actor,
            target_id=report.id,
            trace_code=trace_code,
            client_ip=address,
            before={"state": Report.State.PENDING},
            after={
                "comment_changed": changed,
                "image_count": image_count,
                "outcome": normalized_outcome.value,
                "reason_provided": bool(normalized_reason),
                "snapshot_created": snapshot_created,
                "state": report.state,
            },
            summary="Administrator reviewed report",
        )
        enqueue_event(
            REPORT_REVIEWED_V2,
            aggregate_type="report",
            aggregate_id=report.id,
            actor_id=actor,
            trace_code=trace_code,
            payload={
                "target_comment_id": report.target_comment_id,
                "reason": report.reason,
                "description": report_notification_description(report.description),
                "outcome": normalized_outcome.value,
                "decision_reason": normalized_reason,
                "recipient_ids": [str(value) for value in recipients],
            },
            clock=active_clock,
        )

    return ReportReviewResult(
        report_id=report.id,
        state=report.state,
        comment_changed=changed,
        snapshot_created=snapshot_created,
        image_count=image_count,
        recipient_ids=recipients,
    )


def report_recovery_snapshot_access(
    *,
    actor_id,
    report_id: str,
    account_policy: ModerationAccountPolicy | None = None,
) -> ReportRecoverySnapshotAccess:
    try:
        identity = normalize_ulid(report_id)
    except (TypeError, ValueError):
        return ReportRecoverySnapshotAccess(False, False)
    exists = ReportRecoverySnapshot.objects.filter(report_id=identity).exists()
    if not exists:
        return ReportRecoverySnapshotAccess(False, False)
    try:
        actor = UUID(str(actor_id)) if actor_id is not None else None
    except (TypeError, ValueError):
        actor = None
    accounts = account_policy or default_moderation_account_policy()
    can_read = bool(
        actor is not None
        and accounts.is_active_account(actor)
        and accounts.is_administrator(actor)
    )
    return ReportRecoverySnapshotAccess(True, can_read)
