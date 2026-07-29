from dataclasses import dataclass
from hashlib import sha256

from django.db import transaction

from apps.operations.public import record_audit_entry

from ..media_gateway import NavigationMediaError, navigation_media_gateway
from ..models import StaticPage, TrustedEmbedSource
from ..queries import invalidate_public_site_configuration_cache
from .site_common import (
    SiteContentCommandError,
    require_administrator,
    require_version,
)


@dataclass(frozen=True, slots=True)
class StaticPageResult:
    page_type: str
    row_version: int
    published: bool
    changed: bool


@dataclass(frozen=True, slots=True)
class TrustedSourceResult:
    source_key: str
    enabled: bool
    row_version: int
    changed: bool


def _normalized_static_source(content_format: str, source) -> tuple[str, bool]:
    if not isinstance(source, str):
        raise SiteContentCommandError(
            "navigation.static_page_source_invalid.v1", "页面正文不合法。"
        )
    normalized = source.strip()
    if not normalized:
        return "", False
    try:
        rendered = (
            navigation_media_gateway().render_markdown(normalized)
            if content_format == StaticPage.ContentFormat.MARKDOWN
            else navigation_media_gateway().render_rich_text(normalized)
        )
    except NavigationMediaError:
        raise SiteContentCommandError(
            "navigation.static_page_source_invalid.v1",
            "页面正文无法安全渲染。",
        ) from None
    del rendered
    return normalized, True


def _static_snapshot(row: StaticPage) -> dict[str, object]:
    return {
        "page_type": row.page_type,
        "format": row.content_format,
        "published": row.published,
        "source_digest": sha256(row.source.encode("utf-8")).hexdigest(),
        "row_version": row.row_version,
    }


def update_static_page(
    *,
    actor_id,
    page_type,
    content_format,
    source,
    expected_version,
    trace_code: str,
    client_ip: str,
) -> StaticPageResult:
    actor = require_administrator(actor_id)
    try:
        page = StaticPage.PageType(page_type)
        format_value = StaticPage.ContentFormat(content_format)
    except (TypeError, ValueError):
        raise SiteContentCommandError(
            "navigation.static_page_invalid.v1", "静态页面类型或格式不合法。"
        ) from None
    normalized_source, published = _normalized_static_source(format_value, source)
    version = require_version(expected_version)
    with transaction.atomic():
        try:
            row = StaticPage.objects.select_for_update().get(page_type=page)
        except StaticPage.DoesNotExist:
            raise SiteContentCommandError(
                "navigation.static_page_missing.v1", "静态页面不存在。"
            ) from None
        if row.row_version != version:
            raise SiteContentCommandError(
                "navigation.site_edit_conflict.v1",
                "静态页面已被其他操作更新，请刷新后重试。",
            )
        before = _static_snapshot(row)
        changed = (
            row.content_format != format_value
            or row.source != normalized_source
            or row.published != published
        )
        if changed:
            row.content_format = format_value
            row.source = normalized_source
            row.published = published
            row.row_version += 1
            row.save(
                update_fields=(
                    "content_format",
                    "source",
                    "published",
                    "row_version",
                    "updated_at",
                )
            )
            record_audit_entry(
                action="navigation.static_page.update",
                actor_id=actor,
                target_id=row.page_type,
                trace_code=trace_code,
                client_ip=client_ip,
                before=before,
                after=_static_snapshot(row),
                summary="Update public static page",
            )
            transaction.on_commit(invalidate_public_site_configuration_cache)
    return StaticPageResult(row.page_type, row.row_version, row.published, changed)


def set_trusted_embed_source(
    *,
    actor_id,
    source_key,
    enabled,
    expected_version,
    trace_code: str,
    client_ip: str,
) -> TrustedSourceResult:
    actor = require_administrator(actor_id)
    if source_key != "bilibili" or not isinstance(enabled, bool):
        raise SiteContentCommandError(
            "navigation.trusted_source_invalid.v1", "可信来源设置不合法。"
        )
    version = require_version(expected_version)
    with transaction.atomic():
        try:
            row = TrustedEmbedSource.objects.select_for_update().get(
                source_key=source_key
            )
        except TrustedEmbedSource.DoesNotExist:
            raise SiteContentCommandError(
                "navigation.trusted_source_missing.v1", "可信来源不存在。"
            ) from None
        if row.row_version != version:
            raise SiteContentCommandError(
                "navigation.site_edit_conflict.v1",
                "可信来源已被其他操作更新，请刷新后重试。",
            )
        before = {
            "source_key": row.source_key,
            "enabled": row.enabled,
            "row_version": row.row_version,
        }
        changed = row.enabled != enabled
        if changed:
            row.enabled = enabled
            row.row_version += 1
            row.save(update_fields=("enabled", "row_version", "updated_at"))
            record_audit_entry(
                action="navigation.trusted_source.update",
                actor_id=actor,
                target_id=row.source_key,
                trace_code=trace_code,
                client_ip=client_ip,
                before=before,
                after={
                    "source_key": row.source_key,
                    "enabled": row.enabled,
                    "row_version": row.row_version,
                },
                summary="Update trusted embed source",
            )
    return TrustedSourceResult(row.source_key, row.enabled, row.row_version, changed)


__all__ = [
    "StaticPageResult",
    "TrustedSourceResult",
    "set_trusted_embed_source",
    "update_static_page",
]
