from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.public import is_administrator
from apps.core.events import enqueue_event
from apps.core.ids import normalize_ulid
from apps.media.public import (
    BindingInput,
    MediaBindingError,
    MediaPurpose,
    MediaTargetType,
    release_target_assets,
    replace_bindings,
    target_binding_snapshot,
)
from apps.operations.public import record_audit_entry

from ..events import SECTION_CHANGED
from ..models import ArticleRevision, Section
from ..models.section import normalize_section_name


class SectionCommandError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.safe_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class SectionResult:
    section_id: UUID
    name: str
    default_cover_asset_id: str | None = None


@dataclass(frozen=True, slots=True)
class SectionDeleteResult:
    section_id: UUID
    affected_revision_count: int


def _actor(value) -> UUID:
    try:
        actor_id = UUID(str(value))
    except (TypeError, ValueError):
        raise SectionCommandError(
            "content.section_admin_required.v1", "只有管理员可以管理分区。"
        ) from None
    if not is_administrator(actor_id):
        raise SectionCommandError(
            "content.section_admin_required.v1", "只有管理员可以管理分区。"
        )
    return actor_id


def _section_id(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise SectionCommandError(
            "content.section_not_found.v1", "分区不存在。"
        ) from None


def _name(value: str) -> tuple[str, str]:
    try:
        return normalize_section_name(value)
    except ValidationError:
        raise SectionCommandError(
            "content.section_name_invalid.v1", "分区名称须为 1 至 100 个字符。"
        ) from None


def _cover_id(value) -> str | None:
    if value in (None, ""):
        return None
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise SectionCommandError(
            "content.section_cover_invalid.v1", "分区默认封面不合法。"
        ) from None


def _current_cover_id(section_id: UUID) -> str | None:
    return next(
        (
            item.asset_id
            for item in target_binding_snapshot(
                target_type=MediaTargetType.SECTION,
                target_id=str(section_id),
            )
            if item.purpose == MediaPurpose.SECTION_COVER
            and item.state == "ACTIVE"
            and item.slot == "default-cover"
        ),
        None,
    )


def _snapshot(
    section: Section, default_cover_asset_id: str | None
) -> dict[str, object]:
    return {
        "name": section.name,
        "normalized_name": section.normalized_name,
        "default_cover_asset_id": default_cover_asset_id,
    }


def _replace_cover(*, actor_id: UUID, section_id: UUID, asset_id: str | None) -> None:
    inputs = (BindingInput(asset_id, "default-cover"),) if asset_id else ()
    try:
        replace_bindings(
            actor_id=actor_id,
            target_type=MediaTargetType.SECTION,
            target_id=str(section_id),
            inputs=inputs,
            purpose=MediaPurpose.SECTION_COVER,
        )
    except MediaBindingError as error:
        raise SectionCommandError(error.code, error.safe_message) from None


def _event(*, section_id: UUID, actor_id: UUID, trace_code: str, action: str) -> None:
    enqueue_event(
        SECTION_CHANGED,
        aggregate_type="section",
        aggregate_id=str(section_id),
        actor_id=actor_id,
        trace_code=trace_code,
        payload={"action": action},
    )


def create_section(
    *,
    actor_id,
    name: str,
    default_cover_asset_id=None,
    trace_code: str,
    client_ip: str,
) -> SectionResult:
    actor = _actor(actor_id)
    display, normalized = _name(name)
    cover_id = _cover_id(default_cover_asset_id)
    try:
        with transaction.atomic():
            section = Section.objects.create(
                name=display,
                normalized_name=normalized,
            )
            if cover_id:
                _replace_cover(
                    actor_id=actor,
                    section_id=section.id,
                    asset_id=cover_id,
                )
            record_audit_entry(
                action="content.section.create",
                actor_id=actor,
                target_id=str(section.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before={},
                after=_snapshot(section, cover_id),
                summary="Create article section",
            )
            _event(
                section_id=section.id,
                actor_id=actor,
                trace_code=trace_code,
                action="created",
            )
    except IntegrityError:
        raise SectionCommandError(
            "content.section_name_conflict.v1", "分区名称已存在。"
        ) from None
    return SectionResult(section.id, section.name, cover_id)


def rename_section(
    *, actor_id, section_id, name: str, trace_code: str, client_ip: str
) -> SectionResult:
    actor = _actor(actor_id)
    identity = _section_id(section_id)
    display, normalized = _name(name)
    try:
        with transaction.atomic():
            try:
                section = Section.objects.select_for_update().get(pk=identity)
            except Section.DoesNotExist:
                raise SectionCommandError(
                    "content.section_not_found.v1", "分区不存在。"
                ) from None
            cover_id = _current_cover_id(section.id)
            before = _snapshot(section, cover_id)
            section.name = display
            section.normalized_name = normalized
            section.save(update_fields=("name", "normalized_name", "updated_at"))
            record_audit_entry(
                action="content.section.rename",
                actor_id=actor,
                target_id=str(section.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before=before,
                after=_snapshot(section, cover_id),
                summary="Rename article section",
            )
            _event(
                section_id=section.id,
                actor_id=actor,
                trace_code=trace_code,
                action="renamed",
            )
    except IntegrityError:
        raise SectionCommandError(
            "content.section_name_conflict.v1", "分区名称已存在。"
        ) from None
    return SectionResult(section.id, section.name, cover_id)


def update_section(
    *,
    actor_id,
    section_id,
    name: str,
    default_cover_asset_id=None,
    trace_code: str,
    client_ip: str,
) -> SectionResult:
    actor = _actor(actor_id)
    identity = _section_id(section_id)
    display, normalized = _name(name)
    cover_id = _cover_id(default_cover_asset_id)
    try:
        with transaction.atomic():
            try:
                section = Section.objects.select_for_update().get(pk=identity)
            except Section.DoesNotExist:
                raise SectionCommandError(
                    "content.section_not_found.v1", "分区不存在。"
                ) from None
            current_cover_id = _current_cover_id(section.id)
            before = _snapshot(section, current_cover_id)
            if current_cover_id != cover_id:
                _replace_cover(
                    actor_id=actor,
                    section_id=section.id,
                    asset_id=cover_id,
                )
            section.name = display
            section.normalized_name = normalized
            section.save(
                update_fields=(
                    "name",
                    "normalized_name",
                    "updated_at",
                )
            )
            record_audit_entry(
                action="content.section.update",
                actor_id=actor,
                target_id=str(section.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before=before,
                after=_snapshot(section, cover_id),
                summary="Update article section",
            )
            _event(
                section_id=section.id,
                actor_id=actor,
                trace_code=trace_code,
                action="updated",
            )
    except IntegrityError:
        raise SectionCommandError(
            "content.section_name_conflict.v1", "分区名称已存在。"
        ) from None
    return SectionResult(section.id, section.name, cover_id)


def delete_section(
    *, actor_id, section_id, trace_code: str, client_ip: str
) -> SectionDeleteResult:
    actor = _actor(actor_id)
    identity = _section_id(section_id)
    with transaction.atomic():
        try:
            section = Section.objects.select_for_update().get(pk=identity)
        except Section.DoesNotExist:
            raise SectionCommandError(
                "content.section_not_found.v1", "分区不存在。"
            ) from None
        before = _snapshot(section, _current_cover_id(section.id))
        affected = section.revisions.count()
        release_target_assets(
            target_type=MediaTargetType.SECTION,
            target_ids=(str(section.id),),
        )
        record_audit_entry(
            action="content.section.delete",
            actor_id=actor,
            target_id=str(section.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after={"deleted": True},
            summary="Delete article section",
        )
        _event(
            section_id=section.id,
            actor_id=actor,
            trace_code=trace_code,
            action="deleted",
        )
        section.delete()
    return SectionDeleteResult(identity, affected)


def validate_publication_section(
    revision: ArticleRevision,
    *,
    allow_unknown_import: bool = False,
) -> None:
    if not isinstance(revision, ArticleRevision):
        raise TypeError("revision must be an ArticleRevision")
    if type(allow_unknown_import) is not bool:
        raise TypeError("allow_unknown_import must be a boolean")
    if revision.section_id is None and not allow_unknown_import:
        raise SectionCommandError(
            "content.section_required.v1", "发布文章前必须选择一个分区。"
        )
