from dataclasses import dataclass

from django.db import transaction

from apps.operations.public import record_audit_entry

from ..media_gateway import NavigationMediaError, navigation_media_gateway
from ..models import SiteConfiguration
from ..queries import invalidate_public_site_configuration_cache
from .site_common import (
    SiteContentCommandError,
    normalized_text,
    require_administrator,
    require_version,
)


@dataclass(frozen=True, slots=True)
class SiteConfigurationResult:
    row_version: int
    changed: bool


def _body_limit(value) -> int:
    if isinstance(value, bool):
        raise SiteContentCommandError(
            "navigation.article_body_limit_invalid.v1",
            "正文上限须在 64 KiB 至 2 MiB 之间。",
        )
    try:
        maximum = int(value)
    except (TypeError, ValueError):
        raise SiteContentCommandError(
            "navigation.article_body_limit_invalid.v1",
            "正文上限须在 64 KiB 至 2 MiB 之间。",
        ) from None
    if not (
        SiteConfiguration.MIN_ARTICLE_BODY_BYTES
        <= maximum
        <= SiteConfiguration.MAX_ARTICLE_BODY_BYTES
    ):
        raise SiteContentCommandError(
            "navigation.article_body_limit_invalid.v1",
            "正文上限须在 64 KiB 至 2 MiB 之间。",
        )
    return maximum


def _configuration_snapshot(row: SiteConfiguration) -> dict[str, object]:
    return {
        "site_name": row.site_name,
        "site_description": row.site_description,
        "copyright_text": row.copyright_text,
        "registration_enabled": row.registration_enabled,
        "article_text_limit_bytes": row.article_body_max_bytes,
        "logo_asset_id": row.logo_asset_id,
        "backup_destination": row.backup_destination,
        "row_version": row.row_version,
    }


def update_site_configuration(
    *,
    actor_id,
    site_name,
    site_description,
    copyright_text,
    registration_enabled,
    article_body_max_bytes,
    logo_asset_id,
    backup_destination,
    expected_version,
    trace_code: str,
    client_ip: str,
) -> SiteConfigurationResult:
    actor = require_administrator(actor_id)
    name = normalized_text(site_name, field="站点名称", maximum=100, required=True)
    description = normalized_text(
        site_description, field="站点描述", maximum=200, required=False
    )
    copyright_value = normalized_text(
        copyright_text, field="版权信息", maximum=200, required=False
    )
    if not isinstance(registration_enabled, bool):
        raise SiteContentCommandError(
            "navigation.registration_setting_invalid.v1", "注册开关不合法。"
        )
    maximum = _body_limit(article_body_max_bytes)
    logo_id = str(logo_asset_id).strip() if logo_asset_id else None
    if backup_destination != "local":
        raise SiteContentCommandError(
            "navigation.backup_destination_invalid.v1",
            "首版备份目标只能使用 local。",
        )
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
        before = _configuration_snapshot(row)
        values = {
            "site_name": name,
            "site_description": description,
            "copyright_text": copyright_value,
            "registration_enabled": registration_enabled,
            "article_body_max_bytes": maximum,
            "logo_asset_id": logo_id,
            "backup_destination": "local",
        }
        changed = any(getattr(row, key) != value for key, value in values.items())
        if changed:
            try:
                navigation_media_gateway().replace_site_logo(actor, logo_id)
            except NavigationMediaError as error:
                raise SiteContentCommandError(error.code, error.safe_message) from None
            for key, value in values.items():
                setattr(row, key, value)
            row.row_version += 1
            row.save(update_fields=(*values, "row_version", "updated_at"))
            record_audit_entry(
                action="navigation.site_configuration.update",
                actor_id=actor,
                target_id="site",
                trace_code=trace_code,
                client_ip=client_ip,
                before=before,
                after=_configuration_snapshot(row),
                summary="Update public site configuration",
            )
            transaction.on_commit(invalidate_public_site_configuration_cache)
    return SiteConfigurationResult(row.row_version, changed)


__all__ = [
    "SiteConfigurationResult",
    "update_site_configuration",
]
