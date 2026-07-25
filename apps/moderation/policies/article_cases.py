from django.db.models import Q, QuerySet

from ..models import ArticleModerationCase

_EFFECTIVE = Q(state__in=("ACTIVE", "APPEALED", "FINAL_UPHELD")) | (
    Q(state="FINAL_REJECTED") & ~Q(recovery_error_code="")
)


def article_is_moderation_hidden(article_id: str) -> bool:
    return ArticleModerationCase.objects.filter(
        _EFFECTIVE,
        article_id=article_id,
        action=ArticleModerationCase.Action.HIDE,
    ).exists()


def exclude_moderation_hidden_articles(queryset: QuerySet) -> QuerySet:
    hidden_ids = ArticleModerationCase.objects.filter(
        _EFFECTIVE,
        action=ArticleModerationCase.Action.HIDE,
    ).values("article_id")
    return queryset.exclude(id__in=hidden_ids)
