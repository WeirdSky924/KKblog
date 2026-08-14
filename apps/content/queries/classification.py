from dataclasses import dataclass
from uuid import UUID

from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

from apps.media.public import (
    MediaPurpose,
    MediaTargetType,
    target_binding_snapshots,
)

from ..models import ArticleTag, Section, Tag


@dataclass(frozen=True, slots=True)
class SectionItem:
    section_id: UUID
    name: str
    default_cover_asset_id: str | None


def section_default_cover_schema_ready() -> bool:
    return (
        MigrationRecorder(connection)
        .migration_qs.filter(
            app="media",
            name="0005_remove_mediabinding_media_binding_target_registered_and_more",
        )
        .exists()
    )


def section_cover_asset_ids(section_ids: tuple[str, ...]) -> dict[str, str | None]:
    snapshots = target_binding_snapshots(
        target_type=MediaTargetType.SECTION,
        target_ids=section_ids,
    )
    return {
        section_id: next(
            (
                item.asset_id
                for item in snapshots[section_id]
                if item.purpose == MediaPurpose.SECTION_COVER
                and item.state == "ACTIVE"
                and item.slot == "default-cover"
            ),
            None,
        )
        for section_id in section_ids
    }


def section_list() -> tuple[SectionItem, ...]:
    rows = tuple(Section.objects.order_by("normalized_name", "id").values("id", "name"))
    cover_ids = section_cover_asset_ids(tuple(str(row["id"]) for row in rows))
    return tuple(
        SectionItem(row["id"], row["name"], cover_ids[str(row["id"])]) for row in rows
    )


def section_by_id(section_id) -> SectionItem | None:
    try:
        row = Section.objects.values("id", "name").get(pk=section_id)
    except (Section.DoesNotExist, ValueError, TypeError):
        return None
    identity = str(row["id"])
    return SectionItem(
        row["id"],
        row["name"],
        section_cover_asset_ids((identity,))[identity],
    )


@dataclass(frozen=True, slots=True)
class TagItem:
    tag_id: UUID
    name: str
    state: str


def tags_for_article(article_id: str) -> tuple[TagItem, ...]:
    return tuple(
        TagItem(row.tag_id, row.tag.name, row.tag.state)
        for row in ArticleTag.objects.select_related("tag")
        .filter(article_id=article_id)
        .order_by("tag__normalized_name", "tag_id")
    )


def active_tag(tag_id) -> TagItem | None:
    try:
        tag = Tag.objects.get(pk=tag_id, state=Tag.State.ACTIVE)
    except (Tag.DoesNotExist, ValueError, TypeError):
        return None
    return TagItem(tag.id, tag.name, tag.state)


def tag_reference(tag_id) -> TagItem | None:
    try:
        tag = Tag.objects.get(pk=tag_id)
    except (Tag.DoesNotExist, ValueError, TypeError):
        return None
    return TagItem(tag.id, tag.name, tag.state)


def selectable_tag_list() -> tuple[TagItem, ...]:
    return tuple(
        TagItem(tag.id, tag.name, tag.state)
        for tag in Tag.objects.filter(
            state__in=(Tag.State.PENDING, Tag.State.ACTIVE)
        ).order_by("normalized_name", "id")
    )
