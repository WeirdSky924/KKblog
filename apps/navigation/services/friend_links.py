from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from django.db import transaction
from django.db.models import F

from apps.operations.public import record_audit_entry

from ..media_gateway import NavigationMediaError, navigation_media_gateway
from ..models import FriendLink
from ..validators import normalize_external_navigation_url
from .site_common import (
    SiteContentCommandError,
    normalized_text,
    require_administrator,
    require_version,
)


@dataclass(frozen=True, slots=True)
class FriendLinkResult:
    link_id: UUID
    row_version: int
    position: int


def _identity(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise SiteContentCommandError(
            "navigation.friend_link_not_found.v1", "友情链接不存在。"
        ) from None


def _position(value, *, maximum: int) -> int:
    if isinstance(value, bool):
        raise SiteContentCommandError(
            "navigation.friend_link_position_invalid.v1", "友情链接位置不合法。"
        )
    try:
        position = int(value)
    except (TypeError, ValueError):
        raise SiteContentCommandError(
            "navigation.friend_link_position_invalid.v1", "友情链接位置不合法。"
        ) from None
    if not 0 <= position <= maximum:
        raise SiteContentCommandError(
            "navigation.friend_link_position_invalid.v1", "友情链接位置不合法。"
        )
    return position


def _values(*, name, url, description, logo_asset_id) -> dict[str, str]:
    label = normalized_text(name, field="站点名称", maximum=80, required=True)
    details = normalized_text(description, field="站点描述", maximum=300, required=True)
    try:
        target = normalize_external_navigation_url(url)
    except ValueError as error:
        raise SiteContentCommandError(
            "navigation.friend_link_url_invalid.v1", str(error)
        ) from None
    logo_id = str(logo_asset_id).strip() if logo_asset_id else ""
    if not logo_id:
        raise SiteContentCommandError(
            "navigation.friend_link_logo_required.v1", "友情链接必须设置 Logo。"
        )
    return {
        "name": label,
        "url": target,
        "description": details,
        "logo_asset_id": logo_id,
    }


def _snapshot(row: FriendLink) -> dict[str, object]:
    return {
        "name": row.name,
        "url_host": urlsplit(row.url).hostname or "external",
        "position": row.position,
        "logo_asset_id": row.logo_asset_id,
        "row_version": row.row_version,
    }


def _temporarily_clear_positions(rows: list[FriendLink]) -> None:
    if not rows:
        return
    offset = max(row.position for row in rows) + len(rows) + 1
    FriendLink.objects.filter(pk__in=(row.id for row in rows)).update(
        position=F("position") + offset
    )


def _save_order(
    rows: list[FriendLink],
    *,
    actor_id: UUID,
    before: dict[UUID, dict[str, object]],
    primary_id: UUID,
    primary_action: str,
    trace_code: str,
    client_ip: str,
    primary_description_before: str | None = None,
) -> None:
    for position, row in enumerate(rows):
        old = before.get(row.id, {})
        changed = (
            not old
            or row.position != position
            or (
                row.id == primary_id
                and primary_description_before is not None
                and row.description != primary_description_before
            )
            or any(
                old.get(key) != value
                for key, value in _snapshot(row).items()
                if key not in {"position", "row_version"}
            )
        )
        row.position = position
        if changed:
            row.row_version += 1
            row.save(
                update_fields=(
                    "name",
                    "url",
                    "description",
                    "logo_asset_id",
                    "position",
                    "row_version",
                    "updated_at",
                )
            )
            record_audit_entry(
                action=(
                    primary_action
                    if row.id == primary_id
                    else "navigation.friend_link.reorder"
                ),
                actor_id=actor_id,
                target_id=str(row.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before=old,
                after=_snapshot(row),
                summary="Update public friend link",
            )
        else:
            FriendLink.objects.filter(pk=row.id).update(position=position)


def create_friend_link(
    *,
    actor_id,
    name,
    url,
    description,
    logo_asset_id,
    position,
    trace_code: str,
    client_ip: str,
) -> FriendLinkResult:
    actor = require_administrator(actor_id)
    values = _values(
        name=name,
        url=url,
        description=description,
        logo_asset_id=logo_asset_id,
    )
    with transaction.atomic():
        rows = list(FriendLink.objects.select_for_update().order_by("position", "id"))
        target_position = _position(position, maximum=len(rows))
        before = {row.id: _snapshot(row) for row in rows}
        temporary_position = (rows[-1].position + 1 if rows else 0) + len(rows) + 1
        link = FriendLink.objects.create(position=temporary_position, **values)
        try:
            navigation_media_gateway().replace_friend_logo(
                actor, str(link.id), values["logo_asset_id"]
            )
        except NavigationMediaError as error:
            raise SiteContentCommandError(error.code, error.safe_message) from None
        rows.insert(target_position, link)
        _temporarily_clear_positions(rows)
        _save_order(
            rows,
            actor_id=actor,
            before=before,
            primary_id=link.id,
            primary_action="navigation.friend_link.create",
            trace_code=trace_code,
            client_ip=client_ip,
        )
    return FriendLinkResult(link.id, link.row_version, link.position)


def update_friend_link(
    *,
    actor_id,
    link_id,
    name,
    url,
    description,
    logo_asset_id,
    position,
    expected_version,
    trace_code: str,
    client_ip: str,
) -> FriendLinkResult:
    actor = require_administrator(actor_id)
    identity = _identity(link_id)
    version = require_version(expected_version)
    values = _values(
        name=name,
        url=url,
        description=description,
        logo_asset_id=logo_asset_id,
    )
    with transaction.atomic():
        rows = list(FriendLink.objects.select_for_update().order_by("position", "id"))
        try:
            link = next(row for row in rows if row.id == identity)
        except StopIteration:
            raise SiteContentCommandError(
                "navigation.friend_link_not_found.v1", "友情链接不存在。"
            ) from None
        if link.row_version != version:
            raise SiteContentCommandError(
                "navigation.site_edit_conflict.v1",
                "友情链接已被其他操作更新，请刷新后重试。",
            )
        primary_description_before = link.description
        target_position = _position(position, maximum=len(rows) - 1)
        before = {row.id: _snapshot(row) for row in rows}
        if link.logo_asset_id != values["logo_asset_id"]:
            try:
                navigation_media_gateway().replace_friend_logo(
                    actor, str(link.id), values["logo_asset_id"]
                )
            except NavigationMediaError as error:
                raise SiteContentCommandError(error.code, error.safe_message) from None
        for key, value in values.items():
            setattr(link, key, value)
        rows.remove(link)
        rows.insert(target_position, link)
        _temporarily_clear_positions(rows)
        _save_order(
            rows,
            actor_id=actor,
            before=before,
            primary_id=link.id,
            primary_action="navigation.friend_link.update",
            trace_code=trace_code,
            client_ip=client_ip,
            primary_description_before=primary_description_before,
        )
    return FriendLinkResult(link.id, link.row_version, link.position)


def delete_friend_link(
    *,
    actor_id,
    link_id,
    expected_version,
    trace_code: str,
    client_ip: str,
) -> FriendLinkResult:
    actor = require_administrator(actor_id)
    identity = _identity(link_id)
    version = require_version(expected_version)
    with transaction.atomic():
        rows = list(FriendLink.objects.select_for_update().order_by("position", "id"))
        try:
            link = next(row for row in rows if row.id == identity)
        except StopIteration:
            raise SiteContentCommandError(
                "navigation.friend_link_not_found.v1", "友情链接不存在。"
            ) from None
        if link.row_version != version:
            raise SiteContentCommandError(
                "navigation.site_edit_conflict.v1",
                "友情链接已被其他操作更新，请刷新后重试。",
            )
        before = _snapshot(link)
        try:
            navigation_media_gateway().release_friend_logo(str(link.id))
        except NavigationMediaError as error:
            raise SiteContentCommandError(error.code, error.safe_message) from None
        rows.remove(link)
        _temporarily_clear_positions(rows)
        _save_order(
            rows,
            actor_id=actor,
            before={row.id: _snapshot(row) for row in rows},
            primary_id=link.id,
            primary_action="navigation.friend_link.delete",
            trace_code=trace_code,
            client_ip=client_ip,
        )
        link.delete()
        record_audit_entry(
            action="navigation.friend_link.delete",
            actor_id=actor,
            target_id=str(link.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after={"deleted": True},
            summary="Delete public friend link",
        )
    return FriendLinkResult(identity, version + 1, max(0, len(rows) - 1))


__all__ = [
    "FriendLinkResult",
    "create_friend_link",
    "delete_friend_link",
    "update_friend_link",
]
