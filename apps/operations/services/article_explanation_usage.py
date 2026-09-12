from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Account
from apps.core.time.shanghai import shanghai_business_date

from ..models import ArticleExplanationUsage

_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}\Z")


class ArticleExplanationUsageError(ValueError):
    def __init__(
        self,
        message: str = "文章解释使用记录不可用。",
        *,
        code: str = "operations.article_explanation_usage_invalid.v1",
    ) -> None:
        super().__init__(message)
        self.code = code


class ArticleExplanationRateLimitError(ArticleExplanationUsageError):
    def __init__(self, kind: str, *, retry_after: int | None = None) -> None:
        if kind not in {"daily", "minute"}:
            raise ValueError("invalid article explanation rate limit kind")
        self.kind = kind
        self.retry_after = retry_after
        label = "每日" if kind == "daily" else "每分钟"
        super().__init__(
            f"已达到{label}文章解释次数限制，请稍后再试。",
            code=f"operations.article_explanation_{kind}_limit.v1",
        )


@dataclass(frozen=True, slots=True)
class ArticleExplanationUsageResult:
    usage_id: str
    reused: bool
    counted_toward_limit: bool


def _account_id(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ArticleExplanationUsageError("账户标识无效。") from None


def _key(value: object) -> str:
    if not isinstance(value, str) or not _IDEMPOTENCY_KEY.fullmatch(value):
        raise ArticleExplanationUsageError("幂等标识无效。")
    return value


def _moment(value: datetime | None) -> datetime:
    current = value or timezone.now()
    if not timezone.is_aware(current):
        raise ArticleExplanationUsageError("使用时间无效。")
    return current


def _result(
    row: ArticleExplanationUsage, *, reused: bool
) -> ArticleExplanationUsageResult:
    return ArticleExplanationUsageResult(
        usage_id=row.id,
        reused=reused,
        counted_toward_limit=row.counts_toward_limit,
    )


def reserve_article_explanation_usage(
    *,
    account_id,
    idempotency_key,
    retry_of: str | None = None,
    now: datetime | None = None,
) -> ArticleExplanationUsageResult:
    account_identity = _account_id(account_id)
    stable_key = _key(idempotency_key)
    retry_key = _key(retry_of) if retry_of is not None else None
    current = _moment(now)
    usage_date = shanghai_business_date(current)
    cutoff = current - timedelta(seconds=60)

    with transaction.atomic():
        try:
            account = Account.objects.select_for_update().get(
                pk=account_identity,
                status=Account.Status.ACTIVE,
            )
        except Account.DoesNotExist:
            raise ArticleExplanationUsageError("账户当前不可使用文章解释。") from None

        existing = (
            ArticleExplanationUsage.objects.select_for_update()
            .filter(idempotency_key=stable_key)
            .first()
        )
        if existing is not None:
            if existing.account_id != account.id:
                raise ArticleExplanationUsageError("幂等标识已属于其他账户。")
            return _result(existing, reused=True)

        if retry_key is not None:
            try:
                original = ArticleExplanationUsage.objects.select_for_update().get(
                    idempotency_key=retry_key
                )
            except ArticleExplanationUsage.DoesNotExist:
                raise ArticleExplanationUsageError("原始解释请求不存在。") from None
            if original.account_id != account.id or original.retry_of_id is not None:
                raise ArticleExplanationUsageError("原始解释请求不可重试。")
            if not original.retry_allowed:
                raise ArticleExplanationUsageError("当前解释请求不允许重试。")
            row = ArticleExplanationUsage.objects.create(
                account=account,
                idempotency_key=stable_key,
                retry_of=original,
                usage_date=usage_date,
                occurred_at=current,
                counts_toward_limit=False,
            )
            return _result(row, reused=False)

        try:
            from apps.navigation.queries.article_explanation import (
                ArticleExplanationSettingsQueryError,
                article_explanation_settings,
            )

            limits = article_explanation_settings()
        except ArticleExplanationSettingsQueryError:
            raise ArticleExplanationUsageError(
                "文章解释配置暂时不可用。",
                code="operations.article_explanation_configuration_unavailable.v1",
            ) from None

        daily_count = ArticleExplanationUsage.objects.filter(
            account_id=account.id,
            usage_date=usage_date,
            counts_toward_limit=True,
        ).count()
        if daily_count >= limits.daily_limit:
            raise ArticleExplanationRateLimitError("daily")

        minute_count = ArticleExplanationUsage.objects.filter(
            account_id=account.id,
            occurred_at__gte=cutoff,
            occurred_at__lte=current,
            counts_toward_limit=True,
        ).count()
        if minute_count >= limits.minute_limit:
            raise ArticleExplanationRateLimitError("minute", retry_after=60)

        row = ArticleExplanationUsage.objects.create(
            account=account,
            idempotency_key=stable_key,
            usage_date=usage_date,
            occurred_at=current,
            counts_toward_limit=True,
        )
    return _result(row, reused=False)


def allow_article_explanation_retry(*, usage_id: str) -> bool:
    """Mark one terminal provider failure as eligible for one or more retries."""

    if not isinstance(usage_id, str) or not usage_id:
        raise ArticleExplanationUsageError("使用记录标识无效。")
    with transaction.atomic():
        try:
            row = ArticleExplanationUsage.objects.select_for_update().get(pk=usage_id)
        except ArticleExplanationUsage.DoesNotExist:
            raise ArticleExplanationUsageError("使用记录不存在。") from None
        if row.retry_of_id is not None:
            raise ArticleExplanationUsageError("重试记录不能再次授权重试。")
        if row.retry_allowed:
            return False
        row.retry_allowed = True
        row.save(update_fields=("retry_allowed",))
    return True


__all__ = [
    "ArticleExplanationRateLimitError",
    "ArticleExplanationUsageError",
    "ArticleExplanationUsageResult",
    "allow_article_explanation_retry",
    "reserve_article_explanation_usage",
]
