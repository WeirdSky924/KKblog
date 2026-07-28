from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.db.models import Count

from apps.accounts.public import (
    AccountDeletionDisposition,
    AuthorArticleDecision,
    is_administrator,
)
from apps.core.events import enqueue_event
from apps.core.ids import new_ulid
from apps.media.public import MediaTargetType, release_target_assets

from ..events import ARTICLE_PURGE_REQUESTED
from ..models import Article, ArticleTombstone, AuthorContentMask
from ..purge_ports import ArticleCommentPurgeResult, purge_article_comments


class AccountArticleDispositionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AdminAuthorArticleCount:
    account_id: UUID
    article_count: int


def _administrator(value) -> UUID:
    try:
        actor_id = UUID(str(value))
    except (TypeError, ValueError):
        raise PermissionError("Administrator access required") from None
    if not is_administrator(actor_id):
        raise PermissionError("Administrator access required")
    return actor_id


def _account_id(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise AccountArticleDispositionError("账户不存在") from None


def _expected_count(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AccountArticleDispositionError("作者文章数量无效")
    return value


def admin_author_article_counts(
    *, actor_id, account_ids
) -> tuple[AdminAuthorArticleCount, ...]:
    _administrator(actor_id)
    if account_ids is None or isinstance(account_ids, str | bytes):
        raise AccountArticleDispositionError("账户范围无效")
    try:
        identities = tuple(dict.fromkeys(_account_id(value) for value in account_ids))
    except TypeError:
        raise AccountArticleDispositionError("账户范围无效") from None
    if len(identities) > 100:
        raise AccountArticleDispositionError("账户范围过大")
    counts = {
        row["author_id"]: row["article_count"]
        for row in Article.objects.filter(author_id__in=identities)
        .values("author_id")
        .annotate(article_count=Count("id"))
    }
    return tuple(
        AdminAuthorArticleCount(identity, counts.get(identity, 0))
        for identity in identities
    )


def prepare_account_deletion_disposition(
    *, actor_id, account_id, expected_article_count: int
) -> AccountDeletionDisposition:
    _administrator(actor_id)
    identity = _account_id(account_id)
    expected = _expected_count(expected_article_count)
    article_count = Article.objects.filter(author_id=identity).count()
    if article_count != expected:
        raise AccountArticleDispositionError("作者文章数量已变化，请重新确认")
    decision = (
        AuthorArticleDecision.NO_ARTICLES
        if article_count == 0
        else AuthorArticleDecision.DELETE_ALL
    )
    return AccountDeletionDisposition(
        disposition_id=new_ulid(),
        account_id=identity,
        decision=decision,
        article_count=article_count,
    )


def apply_account_deletion_disposition(
    disposition: AccountDeletionDisposition,
) -> bool:
    if not isinstance(disposition, AccountDeletionDisposition):
        return False
    with transaction.atomic():
        articles = tuple(
            Article.objects.select_for_update()
            .filter(author_id=disposition.account_id)
            .order_by("id")
        )
        if len(articles) != disposition.article_count:
            return False
        expected_decision = (
            AuthorArticleDecision.NO_ARTICLES
            if not articles
            else AuthorArticleDecision.DELETE_ALL
        )
        if disposition.decision != expected_decision:
            return False
        for article in articles:
            comment_result = purge_article_comments(article.id)
            if not isinstance(comment_result, ArticleCommentPurgeResult):
                raise TypeError("comment purge returned an invalid result")
            revision_ids = tuple(
                article.revisions.order_by("id").values_list("id", flat=True)
            )
            if revision_ids:
                media_result = release_target_assets(
                    target_type=MediaTargetType.ARTICLE_REVISION,
                    target_ids=revision_ids,
                )
                asset_count = len(media_result.asset_ids)
            else:
                asset_count = 0
            ArticleTombstone.objects.filter(article_id=article.id).delete()
            enqueue_event(
                ARTICLE_PURGE_REQUESTED,
                aggregate_type="article",
                aggregate_id=article.id,
                payload={
                    "asset_count": asset_count,
                    "comment_count": comment_result.comment_count,
                },
            )
            article.delete()
        AuthorContentMask.objects.filter(author_id=disposition.account_id).delete()
        return True


__all__ = [
    "AccountArticleDispositionError",
    "AdminAuthorArticleCount",
    "admin_author_article_counts",
    "apply_account_deletion_disposition",
    "prepare_account_deletion_disposition",
]
