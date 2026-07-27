from dataclasses import dataclass
from uuid import UUID

from ..models import ArticleTag, Section, Tag


@dataclass(frozen=True, slots=True)
class SectionItem:
    section_id: UUID
    name: str


def section_list() -> tuple[SectionItem, ...]:
    return tuple(
        SectionItem(section.id, section.name)
        for section in Section.objects.order_by("normalized_name", "id")
    )


def section_by_id(section_id) -> SectionItem | None:
    try:
        section = Section.objects.get(pk=section_id)
    except (Section.DoesNotExist, ValueError, TypeError):
        return None
    return SectionItem(section.id, section.name)


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
