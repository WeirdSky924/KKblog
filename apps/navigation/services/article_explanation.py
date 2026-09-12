from dataclasses import dataclass

from django.db import transaction

from apps.operations.public import record_audit_entry

from ..models import SiteConfiguration
from .site_common import SiteContentCommandError, require_administrator, require_version

_LIMITS = {
    "daily_limit": (1, 1_000, "每日解释次数"),
    "minute_limit": (1, 60, "每分钟解释次数"),
    "selection_limit": (1, 10_000, "单次选区字符数"),
    "history_limit": (1, 100, "本地历史条数"),
}


@dataclass(frozen=True, slots=True)
class ArticleExplanationSettingsResult:
    row_version: int
    changed: bool


def _limit(value: object, *, field: str) -> int:
    minimum, maximum, label = _LIMITS[field]
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise SiteContentCommandError(
            "navigation.article_explanation_settings_invalid.v1",
            f"{label}须在 {minimum} 至 {maximum} 之间。",
        )
    return value


def _snapshot(row: SiteConfiguration) -> dict[str, object]:
    return {
        "daily_limit": row.article_explanation_daily_limit,
        "minute_limit": row.article_explanation_minute_limit,
        "selection_limit": row.article_explanation_selection_limit,
        "history_limit": row.article_explanation_history_limit,
        "row_version": row.row_version,
    }


def update_article_explanation_settings(
    *,
    actor_id,
    daily_limit,
    minute_limit,
    selection_limit,
    history_limit,
    expected_version,
    trace_code: str,
    client_ip: str,
) -> ArticleExplanationSettingsResult:
    actor = require_administrator(actor_id)
    values = {
        "article_explanation_daily_limit": _limit(daily_limit, field="daily_limit"),
        "article_explanation_minute_limit": _limit(minute_limit, field="minute_limit"),
        "article_explanation_selection_limit": _limit(
            selection_limit, field="selection_limit"
        ),
        "article_explanation_history_limit": _limit(
            history_limit, field="history_limit"
        ),
    }
    version = require_version(expected_version)
    with transaction.atomic():
        try:
            row = SiteConfiguration.objects.select_for_update().get(pk=1)
        except SiteConfiguration.DoesNotExist:
            raise SiteContentCommandError(
                "navigation.site_configuration_missing.v1", "站点设置不可用。"
            ) from None
        if row.row_version != version:
            raise SiteContentCommandError(
                "navigation.site_edit_conflict.v1",
                "站点设置已被其他操作更新，请刷新后重试。",
            )
        before = _snapshot(row)
        changed = any(getattr(row, key) != value for key, value in values.items())
        if changed:
            for key, value in values.items():
                setattr(row, key, value)
            row.row_version += 1
            row.save(update_fields=(*values, "row_version", "updated_at"))
            record_audit_entry(
                action="navigation.article_explanation_settings.update",
                actor_id=actor,
                target_id="site",
                trace_code=trace_code,
                client_ip=client_ip,
                before=before,
                after=_snapshot(row),
                summary="Update article explanation settings",
            )
    return ArticleExplanationSettingsResult(row.row_version, changed)


__all__ = [
    "ArticleExplanationSettingsResult",
    "update_article_explanation_settings",
]
