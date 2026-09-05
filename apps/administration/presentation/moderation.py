from dataclasses import dataclass
from uuid import UUID

from apps.accounts.public import public_account_identities
from apps.comments.public import (
    GUESTBOOK_TARGET_ID,
    AdminCommentItem,
    AdminCommentThreadItem,
)
from apps.content.public import AdminArticleItem
from apps.moderation.public import ArticleCaseListItem


def account_labels(account_ids) -> dict[UUID, str]:
    identities = tuple(dict.fromkeys(value for value in account_ids if value))
    return {
        identity.account_id: identity.display_name
        for identity in public_account_identities(identities)
    }


def account_label(labels: dict[UUID, str], account_id: UUID | None) -> str:
    if account_id is None:
        return "访客"
    return labels.get(account_id, "已删除或禁用账户")


@dataclass(frozen=True, slots=True)
class AdminArticleRow:
    article: AdminArticleItem
    author_label: str
    case: ArticleCaseListItem | None
    can_hide: bool
    can_delete: bool
    can_restore: bool
    can_review_appeal: bool


def admin_article_rows(
    *,
    articles: tuple[AdminArticleItem, ...],
    cases: tuple[ArticleCaseListItem, ...],
    actor_id,
) -> tuple[AdminArticleRow, ...]:
    labels = account_labels(tuple(article.author_id for article in articles))
    latest_cases: dict[str, ArticleCaseListItem] = {}
    for case in cases:
        latest_cases.setdefault(case.article_id, case)
    rows = []
    for article in articles:
        case = latest_cases.get(article.id)
        own_article = str(article.author_id) == str(actor_id)
        effective_case = case is not None and case.state in {
            "ACTIVE",
            "APPEALED",
            "FINAL_UPHELD",
        }
        rows.append(
            AdminArticleRow(
                article=article,
                author_label=account_label(labels, article.author_id),
                case=case,
                can_hide=article.can_hide and not effective_case and not own_article,
                can_delete=article.can_delete
                and not effective_case
                and not own_article,
                can_restore=bool(case is not None and case.state == "ACTIVE")
                or bool(
                    article.can_restore_deleted
                    and (case is None or case.state == "RESTORED")
                ),
                can_review_appeal=bool(
                    case is not None
                    and case.state == "APPEALED"
                    and case.appeal_id is not None
                ),
            )
        )
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class AdminCommentThreadRow:
    thread: AdminCommentThreadItem
    label: str


@dataclass(frozen=True, slots=True)
class AdminCommentRow:
    comment: AdminCommentItem
    target_label: str
    author_label: str


def article_title_map(articles: tuple[AdminArticleItem, ...]) -> dict[str, str]:
    return {article.id: article.title for article in articles}


def target_label(*, target_type: str, target_id: str, titles: dict[str, str]) -> str:
    if target_type == "GUESTBOOK" and target_id == GUESTBOOK_TARGET_ID:
        return "留言板"
    return titles.get(target_id, "文章已永久删除")


def admin_comment_thread_rows(
    *, threads: tuple[AdminCommentThreadItem, ...], titles: dict[str, str]
) -> tuple[AdminCommentThreadRow, ...]:
    return tuple(
        AdminCommentThreadRow(
            thread=thread,
            label=target_label(
                target_type=thread.target_type,
                target_id=thread.target_id,
                titles=titles,
            ),
        )
        for thread in threads
    )


def admin_comment_rows(
    *, comments: tuple[AdminCommentItem, ...], titles: dict[str, str]
) -> tuple[AdminCommentRow, ...]:
    labels = account_labels(
        tuple(comment.author_id for comment in comments if comment.author_id)
    )
    return tuple(
        AdminCommentRow(
            comment=comment,
            target_label=target_label(
                target_type=comment.target_type,
                target_id=comment.target_id,
                titles=titles,
            ),
            author_label=(
                "访客"
                if comment.author_kind == "ANONYMOUS"
                else (
                    "该账号已注销"
                    if comment.author_kind == "DELETED_ACCOUNT"
                    else account_label(labels, comment.author_id)
                )
            ),
        )
        for comment in comments
    )


__all__ = [
    "AdminArticleRow",
    "AdminCommentRow",
    "AdminCommentThreadRow",
    "account_label",
    "account_labels",
    "admin_article_rows",
    "admin_comment_rows",
    "admin_comment_thread_rows",
    "article_title_map",
    "target_label",
]
