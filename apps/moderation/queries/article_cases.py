from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apps.core.ids import normalize_ulid

from ..models import ArticleAppeal, ArticleModerationCase, DeletedAccountIdentity
from ..ports import ModerationAccountPolicy, default_moderation_account_policy


class ArticleCaseNotFound(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class ArticleAppealDetail:
    id: str
    appellant_id: UUID
    statement: str
    state: str
    reviewed_by_id: UUID | None
    reviewed_at: datetime | None
    decision_reason: str
    recovery_error_code: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ArticleCaseListItem:
    id: str
    article_id: str
    author_id: UUID
    author_deleted: bool
    author_deletion_id: str | None
    action: str
    state: str
    reason: str
    acted_at: datetime
    appeal_id: str | None
    appeal_state: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ArticleCaseDetail(ArticleCaseListItem):
    acted_by_id: UUID
    resolved_by_id: UUID | None
    resolved_at: datetime | None
    recovery_error_code: str
    closure_reason: str
    author_deleted_at: datetime | None
    appeal: ArticleAppealDetail | None


def _actor(value, *, account_policy: ModerationAccountPolicy) -> UUID | None:
    try:
        actor = UUID(str(value))
    except (TypeError, ValueError):
        return None
    return actor if account_policy.is_active_account(actor) else None


def _identity(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ArticleCaseNotFound("Article moderation case not found") from None


def _appeal(row: ArticleModerationCase) -> ArticleAppeal | None:
    try:
        return row.appeal
    except ArticleAppeal.DoesNotExist:
        return None


def _appeal_detail(appeal: ArticleAppeal | None) -> ArticleAppealDetail | None:
    if appeal is None:
        return None
    return ArticleAppealDetail(
        id=appeal.id,
        appellant_id=appeal.appellant_id,
        statement=appeal.statement,
        state=appeal.state,
        reviewed_by_id=appeal.reviewed_by_id,
        reviewed_at=appeal.reviewed_at,
        decision_reason=appeal.decision_reason,
        recovery_error_code=appeal.recovery_error_code,
        created_at=appeal.created_at,
    )


def _list_item(
    row: ArticleModerationCase,
    *,
    deleted_identity: DeletedAccountIdentity | None,
) -> ArticleCaseListItem:
    appeal = _appeal(row)
    return ArticleCaseListItem(
        id=row.id,
        article_id=row.article_id,
        author_id=row.author_id,
        author_deleted=deleted_identity is not None,
        author_deletion_id=(
            deleted_identity.deletion_id if deleted_identity is not None else None
        ),
        action=row.action,
        state=row.state,
        reason=row.reason,
        acted_at=row.acted_at,
        appeal_id=appeal.id if appeal is not None else None,
        appeal_state=appeal.state if appeal is not None else None,
        created_at=row.created_at,
    )


def article_case_detail(
    *,
    actor_id,
    case_id: str,
    account_policy: ModerationAccountPolicy | None = None,
) -> ArticleCaseDetail:
    accounts = account_policy or default_moderation_account_policy()
    actor = _actor(actor_id, account_policy=accounts)
    row = (
        ArticleModerationCase.objects.select_related("appeal")
        .filter(pk=_identity(case_id))
        .first()
    )
    if row is None or actor is None:
        raise ArticleCaseNotFound("Article moderation case not found")
    deleted_identity = DeletedAccountIdentity.objects.filter(
        account_id=row.author_id
    ).first()
    is_administrator = accounts.is_administrator(actor)
    if not is_administrator and (
        actor != row.author_id or deleted_identity is not None
    ):
        raise ArticleCaseNotFound("Article moderation case not found")
    item = _list_item(row, deleted_identity=deleted_identity)
    appeal = _appeal(row)
    return ArticleCaseDetail(
        **{
            field: getattr(item, field)
            for field in ArticleCaseListItem.__dataclass_fields__
        },
        acted_by_id=row.acted_by_id,
        resolved_by_id=row.resolved_by_id,
        resolved_at=row.resolved_at,
        recovery_error_code=row.recovery_error_code,
        closure_reason=row.closure_reason,
        author_deleted_at=(
            deleted_identity.deleted_at if deleted_identity is not None else None
        ),
        appeal=_appeal_detail(appeal),
    )


def article_case_list(
    *,
    actor_id,
    state: str = "",
    limit: int = 100,
    article_ids: tuple[str, ...] | None = None,
    account_policy: ModerationAccountPolicy | None = None,
) -> tuple[ArticleCaseListItem, ...]:
    accounts = account_policy or default_moderation_account_policy()
    actor = _actor(actor_id, account_policy=accounts)
    if actor is None or not accounts.is_administrator(actor):
        raise PermissionError("Article moderation case access denied")
    if not 1 <= limit <= 200:
        raise ValueError("Invalid article moderation case query limit")
    if state and state not in ArticleModerationCase.State.values:
        raise ValueError("Invalid article moderation case state")
    queryset = ArticleModerationCase.objects.select_related("appeal")
    if state:
        queryset = queryset.filter(state=state)
    if article_ids is not None:
        try:
            normalized_article_ids = tuple(
                dict.fromkeys(normalize_ulid(value) for value in article_ids)
            )
        except (TypeError, ValueError):
            raise ValueError("Invalid article moderation case article ids") from None
        queryset = queryset.filter(article_id__in=normalized_article_ids)
    rows = list(queryset.order_by("-created_at", "-id")[:limit])
    deleted = {
        row.account_id: row
        for row in DeletedAccountIdentity.objects.filter(
            account_id__in={case.author_id for case in rows}
        )
    }
    return tuple(
        _list_item(row, deleted_identity=deleted.get(row.author_id)) for row in rows
    )


def admin_article_appeal_review_count(
    *,
    actor_id,
    account_policy: ModerationAccountPolicy | None = None,
) -> int:
    accounts = account_policy or default_moderation_account_policy()
    actor = _actor(actor_id, account_policy=accounts)
    if actor is None or not accounts.is_administrator(actor):
        raise PermissionError("Article moderation case access denied")
    return ArticleModerationCase.objects.filter(
        state=ArticleModerationCase.State.APPEALED,
        appeal__state=ArticleAppeal.State.PENDING,
    ).count()
