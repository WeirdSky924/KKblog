from dataclasses import dataclass
from datetime import datetime

from apps.comments.public import OwnerCommentWorkspace, owner_comment_workspace
from apps.content.public import ArticleNotFound, article_for_author
from apps.core.time import to_shanghai


@dataclass(frozen=True, slots=True)
class BufferedCommentCard:
    comment_id: str
    article_id: str
    article_title: str
    author_label: str
    body: str
    visible_at: datetime
    is_reply: bool


@dataclass(frozen=True, slots=True)
class CommentArticleRow:
    article_id: str
    title: str
    comments_enabled: bool
    buffered_count: int
    visible_count: int
    deleted_count: int
    latest_at: datetime | None

    @property
    def total_count(self) -> int:
        return self.buffered_count + self.visible_count + self.deleted_count


@dataclass(frozen=True, slots=True)
class CommentWorkspacePage:
    buffered_items: tuple[BufferedCommentCard, ...]
    articles: tuple[CommentArticleRow, ...]


def _article_titles(actor_id, article_ids: set[str]) -> dict[str, str]:
    titles = {}
    for article_id in sorted(article_ids):
        try:
            article = article_for_author(actor_id=actor_id, article_id=article_id)
        except ArticleNotFound:
            continue
        titles[article_id] = article.title
    return titles


def _page(actor_id, source: OwnerCommentWorkspace) -> CommentWorkspacePage:
    article_ids = {item.article_id for item in source.buffered_items}
    article_ids.update(item.article_id for item in source.articles)
    titles = _article_titles(actor_id, article_ids)
    return CommentWorkspacePage(
        buffered_items=tuple(
            BufferedCommentCard(
                comment_id=item.comment_id,
                article_id=item.article_id,
                article_title=titles[item.article_id],
                author_label=item.author_label,
                body=item.body,
                visible_at=to_shanghai(item.visible_at),
                is_reply=item.is_reply,
            )
            for item in source.buffered_items
            if item.article_id in titles
        ),
        articles=tuple(
            CommentArticleRow(
                article_id=item.article_id,
                title=titles[item.article_id],
                comments_enabled=item.comments_enabled,
                buffered_count=item.buffered_count,
                visible_count=item.visible_count,
                deleted_count=item.deleted_count,
                latest_at=to_shanghai(item.latest_at) if item.latest_at else None,
            )
            for item in source.articles
            if item.article_id in titles
        ),
    )


def comment_workspace_page(*, actor_id) -> CommentWorkspacePage:
    return _page(actor_id, owner_comment_workspace(actor_id=actor_id))
