from dataclasses import dataclass
from enum import StrEnum
from ipaddress import IPv6Address, ip_address
from uuid import UUID

from django.db import IntegrityError, transaction

from apps.comments.public import (
    CommentDeletionError,
    CommentReportRecoveryError,
    delete_comment_for_report,
    restore_comment_from_report,
)
from apps.core.events import enqueue_event
from apps.core.ids import new_ulid, normalize_ulid
from apps.core.time.clock import Clock, SystemClock, require_aware
from apps.operations.public import record_audit_entry

from ..events import REPORT_FINALIZED
from ..models import Report, ReportAppeal, ReportRecoverySnapshot
from ..ports import (
    ModerationAccountPolicy,
    ReportAppealEvidenceError,
    ReportAppealEvidenceGateway,
    ReportAppealEvidenceUpload,
    default_moderation_account_policy,
    default_report_appeal_evidence_gateway,
)


class ReportAppealError(ValueError):
    def __init__(self, code: str, safe_message: str, *, field: str | None = None):
        self.code = code
        self.safe_message = safe_message
        self.field = field
        super().__init__(safe_message)


class ReportFinalReviewOutcome(StrEnum):
    UPHELD = "UPHELD"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class CreateReportAppealResult:
    appeal_id: str
    state: str
    evidence_count: int


@dataclass(frozen=True, slots=True)
class ReportAppealEvidenceAccess:
    exists: bool
    can_bind: bool
    can_read: bool


@dataclass(frozen=True, slots=True)
class ReportFinalReviewResult:
    report_id: str
    appeal_id: str
    state: str
    comment_changed: bool
    snapshot_destroyed: bool
    recovery_status: str
    recipient_ids: tuple[UUID, ...]


def _actor(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ReportAppealError(
            "moderation.appeal_forbidden.v1",
            "当前身份不能处理该申诉。",
        ) from None


def _identity(value, *, code: str) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ReportAppealError(code, "当前申诉不可用。") from None


def _client_ip(value: str) -> str:
    try:
        parsed = ip_address(value)
    except (TypeError, ValueError):
        raise ReportAppealError(
            "moderation.network_invalid.v1",
            "当前网络信息无效。",
        ) from None
    if isinstance(parsed, IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    return str(parsed)


def _text(value, *, decision: bool = False) -> str:
    if not isinstance(value, str):
        raise ReportAppealError(
            "moderation.appeal_text_invalid.v1",
            "说明需为 200 个字符以内的纯文本。",
            field="decision_reason" if decision else "statement",
        )
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    invalid = len(normalized) > 200 or any(
        not character.isprintable() and character not in "\n\t"
        for character in normalized
    )
    if decision:
        invalid = (
            invalid or "<" in normalized or ">" in normalized or "://" in normalized
        )
    if invalid:
        raise ReportAppealError(
            "moderation.decision_reason_invalid.v1"
            if decision
            else "moderation.appeal_text_invalid.v1",
            "说明需为 200 个字符以内的纯文本。",
            field="decision_reason" if decision else "statement",
        )
    return normalized


def _evidence_refs(values) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        try:
            values = tuple(values)
        except TypeError:
            values = ()
    if (
        len(values) > 3
        or len(set(values)) != len(values)
        or any(
            not isinstance(value, str) or not 1 <= len(value) <= 2048
            for value in values
        )
    ):
        raise ReportAppealError(
            "moderation.appeal_evidence_invalid.v1",
            "申诉最多使用三张有效证据图片。",
            field="evidence",
        )
    return values


def _member(
    *,
    actor_id,
    client_ip: str,
    account_policy: ModerationAccountPolicy,
) -> tuple[UUID, str]:
    actor = _actor(actor_id)
    address = _client_ip(client_ip)
    if not account_policy.is_active_account(actor):
        raise ReportAppealError(
            "moderation.account_unavailable.v1",
            "当前账户无法处理申诉。",
        )
    if account_policy.is_ip_blocked(address):
        raise ReportAppealError(
            "moderation.network_restricted.v1",
            "当前网络暂时受限。",
        )
    return actor, address


def _eligible(report: Report, actor: UUID) -> str:
    if report.state == Report.State.REJECTED:
        allowed = actor == report.reporter_id
    elif report.state == Report.State.UPHELD:
        allowed = actor == report.reported_author_id
    else:
        raise ReportAppealError(
            "moderation.appeal_state_conflict.v1",
            "该举报当前不能申诉。",
        )
    if not allowed:
        raise ReportAppealError(
            "moderation.appeal_forbidden.v1",
            "当前身份不能处理该申诉。",
        )
    return report.state


def create_report_appeal(
    *,
    actor_id,
    report_id: str,
    statement: str,
    evidence_refs: tuple[str, ...],
    client_ip: str,
    account_policy: ModerationAccountPolicy | None = None,
    evidence_gateway: ReportAppealEvidenceGateway | None = None,
) -> CreateReportAppealResult:
    accounts = account_policy or default_moderation_account_policy()
    evidence = evidence_gateway or default_report_appeal_evidence_gateway()
    actor, _ = _member(
        actor_id=actor_id,
        client_ip=client_ip,
        account_policy=accounts,
    )
    identity = _identity(report_id, code="moderation.appeal_unavailable.v1")
    normalized_statement = _text(statement)
    normalized_evidence = _evidence_refs(evidence_refs)
    appeal_id = new_ulid()
    try:
        with transaction.atomic():
            report = Report.objects.select_for_update().filter(pk=identity).first()
            if report is None:
                raise ReportAppealError(
                    "moderation.appeal_unavailable.v1",
                    "当前申诉不可用。",
                )
            basis_outcome = _eligible(report, actor)
            appeal = ReportAppeal.objects.create(
                id=appeal_id,
                report=report,
                appellant_id=actor,
                basis_outcome=basis_outcome,
                statement=normalized_statement,
            )
            try:
                asset_ids = evidence.bind_evidence(
                    appeal_id=appeal.id,
                    report_id=report.id,
                    actor_id=actor,
                    evidence_refs=normalized_evidence,
                )
            except ReportAppealEvidenceError as exc:
                raise ReportAppealError(
                    "moderation.appeal_evidence_invalid.v1",
                    exc.safe_message,
                    field="evidence",
                ) from None
            report.state = Report.State.APPEAL_PENDING
            report.save(update_fields=("state", "updated_at"))
    except IntegrityError:
        if ReportAppeal.objects.filter(report_id=identity).exists():
            raise ReportAppealError(
                "moderation.appeal_state_conflict.v1",
                "该举报当前不能申诉。",
            ) from None
        raise
    return CreateReportAppealResult(
        appeal_id=appeal.id,
        state=report.state,
        evidence_count=len(asset_ids),
    )


def stage_report_appeal_evidence(
    *,
    actor_id,
    report_id: str,
    client_ip: str,
    original_name: str,
    declared_content_type: str,
    chunks,
    account_policy: ModerationAccountPolicy | None = None,
    evidence_gateway: ReportAppealEvidenceGateway | None = None,
) -> ReportAppealEvidenceUpload:
    accounts = account_policy or default_moderation_account_policy()
    evidence = evidence_gateway or default_report_appeal_evidence_gateway()
    actor, _ = _member(
        actor_id=actor_id,
        client_ip=client_ip,
        account_policy=accounts,
    )
    identity = _identity(report_id, code="moderation.appeal_unavailable.v1")
    report = Report.objects.filter(pk=identity).first()
    if report is None or ReportAppeal.objects.filter(report_id=identity).exists():
        raise ReportAppealError(
            "moderation.appeal_state_conflict.v1",
            "该举报当前不能申诉。",
        )
    _eligible(report, actor)
    try:
        return evidence.stage_evidence(
            actor_id=actor,
            report_id=report.id,
            original_name=original_name,
            declared_content_type=declared_content_type,
            chunks=chunks,
        )
    except ReportAppealEvidenceError as exc:
        raise ReportAppealError(
            "moderation.appeal_evidence_invalid.v1",
            exc.safe_message,
            field="evidence",
        ) from None


def report_appeal_evidence_access(
    *,
    actor_id,
    appeal_id: str,
    account_policy: ModerationAccountPolicy | None = None,
) -> ReportAppealEvidenceAccess:
    try:
        identity = normalize_ulid(appeal_id)
    except (TypeError, ValueError):
        return ReportAppealEvidenceAccess(False, False, False)
    appeal = ReportAppeal.objects.select_related("report").filter(pk=identity).first()
    if appeal is None:
        return ReportAppealEvidenceAccess(False, False, False)
    try:
        actor = UUID(str(actor_id)) if actor_id is not None else None
    except (TypeError, ValueError):
        actor = None
    accounts = account_policy or default_moderation_account_policy()
    active = actor is not None and accounts.is_active_account(actor)
    appellant = active and actor == appeal.appellant_id
    administrator = active and accounts.is_administrator(actor)
    return ReportAppealEvidenceAccess(
        exists=True,
        can_bind=bool(
            appellant
            and appeal.state == ReportAppeal.State.PENDING
            and appeal.report.state in {Report.State.UPHELD, Report.State.REJECTED}
        ),
        can_read=bool(appellant or administrator),
    )


def _administrator(
    *,
    actor_id,
    client_ip: str,
    account_policy: ModerationAccountPolicy,
) -> tuple[UUID, str]:
    actor, address = _member(
        actor_id=actor_id,
        client_ip=client_ip,
        account_policy=account_policy,
    )
    if not account_policy.is_administrator(actor):
        raise ReportAppealError(
            "moderation.final_review_forbidden.v1",
            "当前身份不能复审举报。",
        )
    return actor, address


def _final_outcome(value) -> ReportFinalReviewOutcome:
    try:
        return ReportFinalReviewOutcome(value)
    except (TypeError, ValueError):
        raise ReportAppealError(
            "moderation.final_outcome_invalid.v1",
            "请选择有效的复审结果。",
        ) from None


def _recipients(report: Report) -> tuple[UUID, ...]:
    return tuple(
        dict.fromkeys(
            value
            for value in (report.reporter_id, report.reported_author_id)
            if value is not None
        )
    )


def finalize_report_appeal(
    *,
    actor_id,
    report_id: str,
    outcome,
    decision_reason: str,
    client_ip: str,
    trace_code: str,
    account_policy: ModerationAccountPolicy | None = None,
    clock: Clock | None = None,
) -> ReportFinalReviewResult:
    accounts = account_policy or default_moderation_account_policy()
    actor, address = _administrator(
        actor_id=actor_id,
        client_ip=client_ip,
        account_policy=accounts,
    )
    identity = _identity(report_id, code="moderation.appeal_unavailable.v1")
    normalized_outcome = _final_outcome(outcome)
    normalized_reason = _text(decision_reason, decision=True)
    active_clock = clock or SystemClock()
    reviewed_at = require_aware(active_clock.now())

    with transaction.atomic():
        report = Report.objects.select_for_update().filter(pk=identity).first()
        if report is None or report.state != Report.State.APPEAL_PENDING:
            raise ReportAppealError(
                "moderation.final_review_state_conflict.v1",
                "该申诉已经完成复审或当前不可用。",
            )
        appeal = ReportAppeal.objects.select_for_update().filter(report=report).first()
        if appeal is None or appeal.state != ReportAppeal.State.PENDING:
            raise ReportAppealError(
                "moderation.final_review_state_conflict.v1",
                "该申诉已经完成复审或当前不可用。",
            )

        snapshot = (
            ReportRecoverySnapshot.objects.select_for_update()
            .filter(report=report)
            .first()
        )
        comment_changed = False
        snapshot_destroyed = False
        recovery_status = "NOT_REQUIRED"
        recovery_error_code = ""
        if normalized_outcome == ReportFinalReviewOutcome.UPHELD:
            if appeal.basis_outcome == ReportAppeal.BasisOutcome.REJECTED:
                try:
                    deletion = delete_comment_for_report(
                        comment_id=report.target_comment_id,
                        actor_id=actor,
                        client_ip=address,
                        account_policy=accounts,
                    )
                except CommentDeletionError:
                    raise ReportAppealError(
                        "moderation.final_target_unavailable.v1",
                        "被举报评论当前无法完成复审。",
                    ) from None
                comment_changed = deletion.changed
            if snapshot is not None:
                snapshot.delete()
                snapshot_destroyed = True
            final_state = Report.State.FINAL_UPHELD
        else:
            final_state = Report.State.FINAL_REJECTED
            if appeal.basis_outcome == ReportAppeal.BasisOutcome.UPHELD:
                if snapshot is None:
                    recovery_status = "FAILED"
                    recovery_error_code = "moderation.recovery_snapshot_missing.v1"
                else:
                    try:
                        recovery = restore_comment_from_report(
                            comment_id=snapshot.comment_id,
                            actor_id=actor,
                            client_ip=address,
                            body=snapshot.body,
                            previous_state=snapshot.previous_state,
                            previous_visible_at=snapshot.previous_visible_at,
                            account_policy=accounts,
                        )
                    except CommentReportRecoveryError as exc:
                        recovery_status = "FAILED"
                        recovery_error_code = exc.code
                    else:
                        comment_changed = recovery.changed
                        recovery_status = "RESTORED"
                        snapshot.delete()
                        snapshot_destroyed = True

        report.state = final_state
        report.save(update_fields=("state", "updated_at"))
        appeal.state = final_state
        appeal.reviewed_by_id = actor
        appeal.reviewed_at = reviewed_at
        appeal.decision_reason = normalized_reason
        appeal.recovery_error_code = recovery_error_code
        appeal.save(
            update_fields=(
                "state",
                "reviewed_by_id",
                "reviewed_at",
                "decision_reason",
                "recovery_error_code",
                "updated_at",
            )
        )
        recipients = _recipients(report)
        record_audit_entry(
            action="moderation.report.final_review",
            actor_id=actor,
            target_id=report.id,
            trace_code=trace_code,
            client_ip=address,
            before={
                "state": Report.State.APPEAL_PENDING,
                "appeal_state": ReportAppeal.State.PENDING,
            },
            after={
                "state": report.state,
                "appeal_state": appeal.state,
                "basis_outcome": appeal.basis_outcome,
                "comment_changed": comment_changed,
                "outcome": final_state,
                "reason_provided": bool(normalized_reason),
                "recovery_status": recovery_status,
                "snapshot_destroyed": snapshot_destroyed,
            },
            summary="Administrator finalized report appeal",
        )
        enqueue_event(
            REPORT_FINALIZED,
            aggregate_type="report",
            aggregate_id=report.id,
            actor_id=actor,
            trace_code=trace_code,
            payload={
                "target_comment_id": report.target_comment_id,
                "outcome": final_state,
                "decision_reason": normalized_reason,
                "recipient_ids": [str(value) for value in recipients],
                "recovery_status": recovery_status,
            },
            clock=active_clock,
        )

    return ReportFinalReviewResult(
        report_id=report.id,
        appeal_id=appeal.id,
        state=report.state,
        comment_changed=comment_changed,
        snapshot_destroyed=snapshot_destroyed,
        recovery_status=recovery_status,
        recipient_ids=recipients,
    )
