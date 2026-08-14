from dataclasses import dataclass
from hashlib import sha256

from django.db import transaction

from apps.accounts.public import (
    EmailTemplateError,
    validate_verification_email_template,
)
from apps.operations.public import record_audit_entry

from ..media_gateway import NavigationMediaError, navigation_media_gateway
from ..models import SiteConfiguration
from ..queries import invalidate_public_site_configuration_cache
from ..schema import site_hero_column_available
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


@dataclass(frozen=True, slots=True)
class VerificationEmailTemplateResult:
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


def _configuration_snapshot(
    row: SiteConfiguration, *, hero_asset_id: str | None
) -> dict[str, object]:
    return {
        "site_name": row.site_name,
        "site_description": row.site_description,
        "copyright_text": row.copyright_text,
        "registration_enabled": row.registration_enabled,
        "article_text_limit_bytes": row.article_body_max_bytes,
        "logo_asset_id": row.logo_asset_id,
        "hero_asset_id": hero_asset_id,
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
    hero_asset_id,
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
    hero_id = str(hero_asset_id).strip() if hero_asset_id else None
    hero_available = site_hero_column_available()
    if hero_id and not hero_available:
        raise SiteContentCommandError(
            "navigation.site_hero_unavailable.v1",
            "首页主视觉配置尚未完成数据升级。",
        )
    if backup_destination != "local":
        raise SiteContentCommandError(
            "navigation.backup_destination_invalid.v1",
            "首版备份目标只能使用 local。",
        )
    version = require_version(expected_version)
    with transaction.atomic():
        try:
            fields = (
                "site_name",
                "site_description",
                "copyright_text",
                "registration_enabled",
                "article_body_max_bytes",
                "logo_asset_id",
                "backup_destination",
                "row_version",
            )
            row = (
                SiteConfiguration.objects.select_for_update()
                .only(*fields, *(("hero_asset_id",) if hero_available else ()))
                .get(pk=1)
            )
        except SiteConfiguration.DoesNotExist:
            raise SiteContentCommandError(
                "navigation.site_configuration_missing.v1", "站点设置不可用。"
            ) from None
        if row.row_version != version:
            raise SiteContentCommandError(
                "navigation.site_edit_conflict.v1",
                "站点设置已被其他操作更新，请刷新后重试。",
            )
        current_hero_id = row.hero_asset_id if hero_available else None
        before = _configuration_snapshot(row, hero_asset_id=current_hero_id)
        values = {
            "site_name": name,
            "site_description": description,
            "copyright_text": copyright_value,
            "registration_enabled": registration_enabled,
            "article_body_max_bytes": maximum,
            "logo_asset_id": logo_id,
            "backup_destination": "local",
        }
        if hero_available:
            values["hero_asset_id"] = hero_id
        changed = any(getattr(row, key) != value for key, value in values.items())
        if changed:
            try:
                media = navigation_media_gateway()
                if row.logo_asset_id != logo_id:
                    media.replace_site_logo(actor, logo_id)
                if hero_available and current_hero_id != hero_id:
                    media.replace_site_hero(actor, hero_id)
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
                after=_configuration_snapshot(
                    row,
                    hero_asset_id=hero_id if hero_available else None,
                ),
                summary="Update public site configuration",
            )
            transaction.on_commit(invalidate_public_site_configuration_cache)
    return SiteConfigurationResult(row.row_version, changed)


def _template_snapshot(row: SiteConfiguration) -> dict[str, object]:
    source = row.verification_email_template
    return {
        "template_customized": bool(source),
        "template_digest": sha256(source.encode("utf-8")).hexdigest() if source else "",
        "row_version": row.row_version,
    }


def update_verification_email_template(
    *,
    actor_id,
    template_source,
    expected_version,
    trace_code: str,
    client_ip: str,
) -> VerificationEmailTemplateResult:
    actor = require_administrator(actor_id)
    if template_source:
        try:
            source = validate_verification_email_template(template_source)
        except EmailTemplateError as error:
            raise SiteContentCommandError(
                "navigation.verification_email_template_invalid.v1", str(error)
            ) from None
    else:
        source = ""
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
        before = _template_snapshot(row)
        changed = row.verification_email_template != source
        if changed:
            row.verification_email_template = source
            row.row_version += 1
            row.save(
                update_fields=(
                    "verification_email_template",
                    "row_version",
                    "updated_at",
                )
            )
            record_audit_entry(
                action="navigation.verification_email_template.update",
                actor_id=actor,
                target_id="site",
                trace_code=trace_code,
                client_ip=client_ip,
                before=before,
                after=_template_snapshot(row),
                summary="Update verification email template",
            )
            transaction.on_commit(invalidate_public_site_configuration_cache)
    return VerificationEmailTemplateResult(row.row_version, changed)


__all__ = [
    "SiteConfigurationResult",
    "VerificationEmailTemplateResult",
    "update_site_configuration",
    "update_verification_email_template",
]
