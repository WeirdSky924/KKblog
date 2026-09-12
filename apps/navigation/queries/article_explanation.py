from dataclasses import dataclass

from ..models import SiteConfiguration


class ArticleExplanationSettingsQueryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ArticleExplanationSettingsItem:
    daily_limit: int
    minute_limit: int
    selection_limit: int
    history_limit: int
    row_version: int


def article_explanation_settings() -> ArticleExplanationSettingsItem:
    try:
        row = SiteConfiguration.objects.only(
            "article_explanation_daily_limit",
            "article_explanation_minute_limit",
            "article_explanation_selection_limit",
            "article_explanation_history_limit",
            "row_version",
        ).get(pk=1)
    except SiteConfiguration.DoesNotExist:
        raise ArticleExplanationSettingsQueryError(
            "Article explanation settings are unavailable"
        ) from None
    return ArticleExplanationSettingsItem(
        daily_limit=row.article_explanation_daily_limit,
        minute_limit=row.article_explanation_minute_limit,
        selection_limit=row.article_explanation_selection_limit,
        history_limit=row.article_explanation_history_limit,
        row_version=row.row_version,
    )


__all__ = [
    "ArticleExplanationSettingsItem",
    "ArticleExplanationSettingsQueryError",
    "article_explanation_settings",
]
