from django.db.models import Q, QuerySet

from apps.core.ids import normalize_ulid

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


def article_administrative_action_allowed(
    *,
    actor_id,
    article_id: str,
    case_id: str | None,
    action: str,
    operation: str,
) -> bool:
    if action not in ArticleModerationCase.Action.values:
        return False
    try:
        identity = normalize_ulid(case_id)
    except (TypeError, ValueError):
        if operation == "APPLY" and case_id is None:
            return True
        if operation == "RESTORE":
            return not ArticleModerationCase.objects.filter(
                _EFFECTIVE,
                article_id=article_id,
                action=action,
            ).exists()
        return False
    if operation == "APPLY":
        allowed_states = (ArticleModerationCase.State.ACTIVE,)
    elif operation == "RESTORE":
        allowed_states = (
            ArticleModerationCase.State.ACTIVE,
            ArticleModerationCase.State.APPEALED,
        )
    else:
        return False
    return ArticleModerationCase.objects.filter(
        pk=identity,
        article_id=article_id,
        acted_by_id=actor_id,
        action=action,
        state__in=allowed_states,
    ).exists()
