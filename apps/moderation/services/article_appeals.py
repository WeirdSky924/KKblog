from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from django.db import IntegrityError, transaction

from apps.content.public import (
    ArticleModerationBoundaryError,
    restore_article_from_moderation,
)
from apps.core.events import enqueue_event
from apps.core.ids import new_ulid, normalize_ulid
from apps.core.time.clock import Clock, SystemClock, require_aware
from apps.operations.public import record_audit_entry

from ..events import ARTICLE_MODERATION_FINALIZED
from ..models import ArticleAppeal, ArticleModerationCase
from ..ports import (
    ArticleAppealEvidenceError,
    ArticleAppealEvidenceGateway,
    ArticleAppealEvidenceUpload,
    ModerationAccountPolicy,
    default_article_appeal_evidence_gateway,
    default_moderation_account_policy,
)
from .article_cases import ArticleCaseError, _actor, _administrator, _client_ip


class ArticleAppealReviewOutcome(StrEnum):
    GRANTED = "GRANTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class CreateArticleAppealResult:
    appeal_id: str
    case_id: str
    state: str
    evidence_count: int


@dataclass(frozen=True, slots=True)
class ArticleAppealEvidenceAccess:
    exists: bool
    can_bind: bool
    can_read: bool


@dataclass(frozen=True, slots=True)
class ArticleAppealReviewResult:
    appeal_id: str
    case_id: str
    article_id: str
    state: str
    article_changed: bool
    recovery_status: str
    recipient_ids: tuple[UUID, ...]


def _identity(value, *, code: str) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ArticleCaseError(code, "当前文章申诉不可用。") from None


def _text(value, *, decision: bool = False) -> str:
    field = "decision_reason" if decision else "statement"
    code = (
        "moderation.article_decision_reason_invalid.v1"
        if decision
        else "moderation.article_appeal_text_invalid.v1"
    )
    if not isinstance(value, str):
        raise ArticleCaseError(
            code,
            "说明需为 200 个字符以内的纯文本。",
            field=field,
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
        raise ArticleCaseError(
            code,
            "说明需为 200 个字符以内的纯文本。",
            field=field,
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
        raise ArticleCaseError(
            "moderation.article_appeal_evidence_invalid.v1",
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
        raise ArticleCaseError(
            "moderation.article_appeal_forbidden.v1",
            "当前身份不能处理该文章申诉。",
        )
    if account_policy.is_ip_blocked(address):
        raise ArticleCaseError(
            "moderation.network_restricted.v1",
            "当前网络暂时受限。",
        )
    return actor, address


def appeal_article_action(
    *,
    actor_id,
    case_id: str,
    statement: str,
    evidence_refs: tuple[str, ...],
    client_ip: str,
    account_policy: ModerationAccountPolicy | None = None,
    evidence_gateway: ArticleAppealEvidenceGateway | None = None,
) -> CreateArticleAppealResult:
    accounts = account_policy or default_moderation_account_policy()
    evidence = evidence_gateway or default_article_appeal_evidence_gateway()
    actor, _ = _member(
        actor_id=actor_id,
        client_ip=client_ip,
        account_policy=accounts,
    )
    identity = _identity(
        case_id,
        code="moderation.article_appeal_unavailable.v1",
    )
    normalized_statement = _text(statement)
    normalized_evidence = _evidence_refs(evidence_refs)
    appeal_id = new_ulid()
    try:
        with transaction.atomic():
            case = (
                ArticleModerationCase.objects.select_for_update()
                .filter(pk=identity)
                .first()
            )
            if case is None or case.state != ArticleModerationCase.State.ACTIVE:
                raise ArticleCaseError(
                    "moderation.article_appeal_state_conflict.v1",
                    "该文章管理动作当前不能申诉。",
                )
            if actor != case.author_id:
                raise ArticleCaseError(
                    "moderation.article_appeal_forbidden.v1",
                    "当前身份不能处理该文章申诉。",
                )
            appeal = ArticleAppeal.objects.create(
                id=appeal_id,
                case=case,
                appellant_id=actor,
                statement=normalized_statement,
            )
            try:
                asset_ids = evidence.bind_evidence(
                    appeal_id=appeal.id,
                    case_id=case.id,
                    actor_id=actor,
                    evidence_refs=normalized_evidence,
                )
            except ArticleAppealEvidenceError as exc:
                raise ArticleCaseError(
                    "moderation.article_appeal_evidence_invalid.v1",
                    exc.safe_message,
                    field="evidence",
                ) from None
            case.state = ArticleModerationCase.State.APPEALED
            case.save(update_fields=("state", "updated_at"))
    except IntegrityError:
        raise ArticleCaseError(
            "moderation.article_appeal_state_conflict.v1",
            "该文章管理动作当前不能申诉。",
        ) from None
    return CreateArticleAppealResult(
        appeal.id,
        case.id,
        case.state,
        len(asset_ids),
    )


def stage_article_appeal_evidence(
    *,
    actor_id,
    case_id: str,
    client_ip: str,
    original_name: str,
    declared_content_type: str,
    chunks,
    account_policy: ModerationAccountPolicy | None = None,
    evidence_gateway: ArticleAppealEvidenceGateway | None = None,
) -> ArticleAppealEvidenceUpload:
    accounts = account_policy or default_moderation_account_policy()
    evidence = evidence_gateway or default_article_appeal_evidence_gateway()
    actor, _ = _member(
        actor_id=actor_id,
        client_ip=client_ip,
        account_policy=accounts,
    )
    identity = _identity(
        case_id,
        code="moderation.article_appeal_unavailable.v1",
    )
    case = ArticleModerationCase.objects.filter(pk=identity).first()
    if (
        case is None
        or case.state != ArticleModerationCase.State.ACTIVE
        or case.author_id != actor
        or ArticleAppeal.objects.filter(case=case).exists()
    ):
        raise ArticleCaseError(
            "moderation.article_appeal_state_conflict.v1",
            "该文章管理动作当前不能申诉。",
        )
    try:
        return evidence.stage_evidence(
            actor_id=actor,
            case_id=case.id,
            original_name=original_name,
            declared_content_type=declared_content_type,
            chunks=chunks,
        )
    except ArticleAppealEvidenceError as exc:
        raise ArticleCaseError(
            "moderation.article_appeal_evidence_invalid.v1",
            exc.safe_message,
            field="evidence",
        ) from None


def article_appeal_evidence_access(
    *,
    actor_id,
    appeal_id: str,
    account_policy: ModerationAccountPolicy | None = None,
) -> ArticleAppealEvidenceAccess:
    try:
        identity = normalize_ulid(appeal_id)
    except (TypeError, ValueError):
        return ArticleAppealEvidenceAccess(False, False, False)
    appeal = ArticleAppeal.objects.select_related("case").filter(pk=identity).first()
    if appeal is None:
        return ArticleAppealEvidenceAccess(False, False, False)
    try:
        actor = UUID(str(actor_id)) if actor_id is not None else None
    except (TypeError, ValueError):
        actor = None
    accounts = account_policy or default_moderation_account_policy()
    active = actor is not None and accounts.is_active_account(actor)
    appellant = active and actor == appeal.appellant_id
    administrator = active and accounts.is_administrator(actor)
    return ArticleAppealEvidenceAccess(
        exists=True,
        can_bind=bool(
            appellant
            and appeal.state == ArticleAppeal.State.PENDING
            and appeal.case.state == ArticleModerationCase.State.ACTIVE
        ),
        can_read=bool(appellant or administrator),
    )


def _outcome(value) -> ArticleAppealReviewOutcome:
    try:
        return ArticleAppealReviewOutcome(value)
    except (TypeError, ValueError):
        raise ArticleCaseError(
            "moderation.article_final_outcome_invalid.v1",
            "请选择有效的复审结果。",
            field="outcome",
        ) from None


def review_article_appeal(
    *,
    actor_id,
    appeal_id: str,
    outcome,
    decision_reason: str,
    client_ip: str,
    trace_code: str,
    account_policy: ModerationAccountPolicy | None = None,
    clock: Clock | None = None,
) -> ArticleAppealReviewResult:
    accounts = account_policy or default_moderation_account_policy()
    actor, address = _administrator(
        actor_id=actor_id,
        client_ip=client_ip,
        account_policy=accounts,
    )
    identity = _identity(
        appeal_id,
        code="moderation.article_appeal_unavailable.v1",
    )
    normalized_outcome = _outcome(outcome)
    normalized_reason = _text(decision_reason, decision=True)
    active_clock = clock or SystemClock()
    reviewed_at = require_aware(active_clock.now())
    with transaction.atomic():
        appeal = ArticleAppeal.objects.select_for_update().filter(pk=identity).first()
        if appeal is None or appeal.state != ArticleAppeal.State.PENDING:
            raise ArticleCaseError(
                "moderation.article_final_review_state_conflict.v1",
                "该文章申诉已经复审或当前不可用。",
            )
        case = (
            ArticleModerationCase.objects.select_for_update()
            .filter(pk=appeal.case_id)
            .first()
        )
        if case is None or case.state != ArticleModerationCase.State.APPEALED:
            raise ArticleCaseError(
                "moderation.article_final_review_state_conflict.v1",
                "该文章申诉已经复审或当前不可用。",
            )
        article_changed = False
        recovery_status = "NOT_REQUIRED"
        recovery_error_code = ""
        if normalized_outcome == ArticleAppealReviewOutcome.GRANTED:
            final_state = ArticleModerationCase.State.FINAL_REJECTED
            try:
                recovery = restore_article_from_moderation(
                    actor_id=actor,
                    article_id=case.article_id,
                    action=case.action,
                    pre_action_snapshot=case.pre_action_snapshot,
                    trace_code=trace_code,
                    client_ip=address,
                    clock=active_clock,
                )
            except ArticleModerationBoundaryError as exc:
                recovery_status = "FAILED"
                recovery_error_code = exc.code
            else:
                recovery_status = "RESTORED"
                article_changed = recovery.changed
        else:
            final_state = ArticleModerationCase.State.FINAL_UPHELD
        case.state = final_state
        case.resolved_by_id = actor
        case.resolved_at = reviewed_at
        case.recovery_error_code = recovery_error_code
        case.save(
            update_fields=(
                "state",
                "resolved_by_id",
                "resolved_at",
                "recovery_error_code",
                "updated_at",
            )
        )
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
        record_audit_entry(
            action="moderation.article.final_review",
            actor_id=actor,
            target_id=case.article_id,
            trace_code=trace_code,
            client_ip=address,
            before={
                "action": case.action,
                "state": ArticleModerationCase.State.APPEALED,
            },
            after={
                "article_changed": article_changed,
                "case_id": case.id,
                "outcome": case.state,
                "reason_provided": bool(normalized_reason),
                "recovery_status": recovery_status,
                "state": case.state,
            },
            summary="Administrator finalized article appeal",
        )
        enqueue_event(
            ARTICLE_MODERATION_FINALIZED,
            aggregate_type="article",
            aggregate_id=case.article_id,
            actor_id=actor,
            trace_code=trace_code,
            payload={
                "case_id": case.id,
                "action": case.action,
                "outcome": case.state,
                "decision_reason": normalized_reason,
                "recipient_id": str(case.author_id),
                "recovery_status": recovery_status,
            },
            clock=active_clock,
        )
    return ArticleAppealReviewResult(
        appeal.id,
        case.id,
        case.article_id,
        case.state,
        article_changed,
        recovery_status,
        (case.author_id,),
    )
