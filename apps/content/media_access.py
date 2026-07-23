from apps.accounts.public import is_active_author
from apps.media.public import (
    MediaTargetType,
    TargetAccessDecision,
    TargetAccessRequest,
    register_target_access,
)

from .models import ArticleRevision


def article_revision_media_access(
    request: TargetAccessRequest,
) -> TargetAccessDecision:
    try:
        revision = ArticleRevision.objects.select_related("article").get(
            pk=request.target_id
        )
    except ArticleRevision.DoesNotExist:
        return TargetAccessDecision(False, False, False, False)
    article = revision.article
    author_active = is_active_author(article.author_id)
    owner = author_active and request.actor_id == article.author_id
    is_published = (
        article.published_revision_id == revision.id
        and article.deleted_at is None
        and author_active
    )
    if revision.visibility == ArticleRevision.Visibility.PUBLIC:
        reader = is_published
    elif revision.visibility == ArticleRevision.Visibility.AUTHENTICATED:
        reader = is_published and request.actor_id is not None
    else:
        reader = False
    return TargetAccessDecision(
        exists=True,
        can_bind=owner and article.deleted_at is None,
        can_read=owner or reader,
        public_immutable=(
            is_published and revision.visibility == ArticleRevision.Visibility.PUBLIC
        ),
        binding_scope=article.id,
    )


def register_media_access() -> None:
    register_target_access(
        MediaTargetType.ARTICLE_REVISION,
        article_revision_media_access,
        replace=True,
    )
