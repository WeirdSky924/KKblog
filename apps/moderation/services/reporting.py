from dataclasses import dataclass
from ipaddress import IPv6Address, ip_address
from uuid import UUID

from django.db import IntegrityError, transaction

from apps.comments.public import CommentReportTargetError, reportable_comment_target
from apps.core.ids import new_ulid, normalize_ulid

from ..models import Report, ReportReason
from ..ports import (
    ModerationAccountPolicy,
    ReportEvidenceError,
    ReportEvidenceGateway,
    ReportEvidenceUpload,
    default_moderation_account_policy,
    default_report_evidence_gateway,
)


class ReportSubmissionError(ValueError):
    def __init__(self, code: str, safe_message: str, *, field: str | None = None):
        self.code = code
        self.safe_message = safe_message
        self.field = field
        super().__init__(safe_message)


@dataclass(frozen=True, slots=True)
class CreateReportResult:
    report_id: str
    state: str
    evidence_count: int


@dataclass(frozen=True, slots=True)
class ReportEvidenceAccess:
    exists: bool
    can_bind: bool
    can_read: bool


def _submission_access(
    *,
    actor_id,
    comment_id: str,
    client_ip: str,
    account_policy: ModerationAccountPolicy,
):
    actor = _actor(actor_id)
    address = _client_ip(client_ip)
    if not account_policy.is_active_account(actor):
        raise ReportSubmissionError(
            "moderation.account_unavailable.v1",
            "当前账户无法提交举报。",
        )
    if account_policy.is_ip_blocked(address):
        raise ReportSubmissionError(
            "moderation.network_restricted.v1",
            "当前网络暂时受限。",
        )
    try:
        target = reportable_comment_target(comment_id=comment_id, actor_id=actor)
    except CommentReportTargetError:
        raise ReportSubmissionError(
            "moderation.target_unavailable.v1",
            "当前评论无法举报。",
        ) from None
    return actor, target


def _actor(value) -> UUID:
    if value is None:
        raise ReportSubmissionError(
            "moderation.login_required.v1",
            "登录后才能举报评论。",
        )
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ReportSubmissionError(
            "moderation.account_unavailable.v1",
            "当前账户无法提交举报。",
        ) from None


def _client_ip(value: str) -> str:
    try:
        parsed = ip_address(value)
    except (TypeError, ValueError):
        raise ReportSubmissionError(
            "moderation.network_invalid.v1",
            "当前网络信息无效。",
        ) from None
    if isinstance(parsed, IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    return str(parsed)


def _reason(value) -> ReportReason:
    try:
        return ReportReason(value)
    except (TypeError, ValueError):
        raise ReportSubmissionError(
            "moderation.reason_invalid.v1",
            "请选择有效的举报理由。",
            field="reason",
        ) from None


def _description(value) -> str:
    if not isinstance(value, str):
        raise ReportSubmissionError(
            "moderation.description_invalid.v1",
            "补充说明不能超过 200 字。",
            field="description",
        )
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(normalized) > 200 or any(
        not char.isprintable() and char not in "\n\t" for char in normalized
    ):
        raise ReportSubmissionError(
            "moderation.description_invalid.v1",
            "补充说明不能超过 200 字。",
            field="description",
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
        raise ReportSubmissionError(
            "moderation.evidence_invalid.v1",
            "举报最多使用三张有效证据图片。",
            field="evidence",
        )
    return values


def _duplicate() -> ReportSubmissionError:
    return ReportSubmissionError(
        "moderation.report_duplicate.v1",
        "你已经举报过这条内容。",
    )


def create_report(
    *,
    actor_id,
    comment_id: str,
    reason,
    description: str,
    evidence_refs: tuple[str, ...],
    client_ip: str,
    account_policy: ModerationAccountPolicy | None = None,
    evidence_gateway: ReportEvidenceGateway | None = None,
) -> CreateReportResult:
    normalized_reason = _reason(reason)
    normalized_description = _description(description)
    normalized_evidence = _evidence_refs(evidence_refs)
    accounts = account_policy or default_moderation_account_policy()
    evidence = evidence_gateway or default_report_evidence_gateway()
    actor, target = _submission_access(
        actor_id=actor_id,
        comment_id=comment_id,
        client_ip=client_ip,
        account_policy=accounts,
    )
    if Report.objects.filter(
        reporter_id=actor,
        target_comment_id=target.comment_id,
    ).exists():
        raise _duplicate()

    report_id = new_ulid()
    try:
        with transaction.atomic():
            report = Report.objects.create(
                id=report_id,
                target_comment_id=target.comment_id,
                reporter_id=actor,
                reported_author_id=target.author_id,
                reason=normalized_reason,
                description=normalized_description,
                state=Report.State.PENDING,
            )
            try:
                asset_ids = evidence.bind_evidence(
                    report_id=report.id,
                    actor_id=actor,
                    target_comment_id=target.comment_id,
                    evidence_refs=normalized_evidence,
                )
            except ReportEvidenceError as exc:
                raise ReportSubmissionError(
                    "moderation.evidence_invalid.v1",
                    exc.safe_message,
                    field="evidence",
                ) from None
    except IntegrityError:
        if Report.objects.filter(
            reporter_id=actor,
            target_comment_id=target.comment_id,
        ).exists():
            raise _duplicate() from None
        raise
    return CreateReportResult(
        report_id=report.id,
        state=report.state,
        evidence_count=len(asset_ids),
    )


def stage_report_evidence(
    *,
    actor_id,
    comment_id: str,
    client_ip: str,
    original_name: str,
    declared_content_type: str,
    chunks,
    account_policy: ModerationAccountPolicy | None = None,
    evidence_gateway: ReportEvidenceGateway | None = None,
) -> ReportEvidenceUpload:
    accounts = account_policy or default_moderation_account_policy()
    evidence = evidence_gateway or default_report_evidence_gateway()
    actor, target = _submission_access(
        actor_id=actor_id,
        comment_id=comment_id,
        client_ip=client_ip,
        account_policy=accounts,
    )
    try:
        return evidence.stage_evidence(
            actor_id=actor,
            target_comment_id=target.comment_id,
            original_name=original_name,
            declared_content_type=declared_content_type,
            chunks=chunks,
        )
    except ReportEvidenceError as exc:
        raise ReportSubmissionError(
            "moderation.evidence_invalid.v1",
            exc.safe_message,
            field="evidence",
        ) from None


def report_evidence_access(
    *,
    actor_id,
    report_id: str,
    account_policy: ModerationAccountPolicy | None = None,
) -> ReportEvidenceAccess:
    try:
        identity = normalize_ulid(report_id)
    except (TypeError, ValueError):
        return ReportEvidenceAccess(False, False, False)
    report = Report.objects.filter(pk=identity).first()
    if report is None:
        return ReportEvidenceAccess(False, False, False)
    try:
        actor = UUID(str(actor_id)) if actor_id is not None else None
    except (TypeError, ValueError):
        actor = None
    accounts = account_policy or default_moderation_account_policy()
    active = actor is not None and accounts.is_active_account(actor)
    reporter = active and actor == report.reporter_id
    administrator = active and accounts.is_administrator(actor)
    return ReportEvidenceAccess(
        exists=True,
        can_bind=bool(reporter and report.state == Report.State.PENDING),
        can_read=bool(reporter or administrator),
    )
