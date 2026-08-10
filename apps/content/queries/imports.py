from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ValidationError

from apps.core.ids import normalize_ulid

from ..models import Article, Section, Tag
from ..models.section import normalize_section_name
from ..models.tag import normalize_tag_name


class ImportContentError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ImportConflictFacts:
    id_owner_id: UUID | None
    exact_title_owner_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ImportMappingFacts:
    section_id: UUID | None
    tag_ids: tuple[UUID, ...]
    proposed_tag_names: tuple[str, ...]


def import_conflict_facts(
    *, imported_article_id: str | None, title: str
) -> ImportConflictFacts:
    if not isinstance(title, str) or not title or len(title) > 30:
        raise ImportContentError("content.import_title_invalid.v1")
    id_owner_id = None
    if imported_article_id is not None:
        try:
            identity = normalize_ulid(imported_article_id)
        except (TypeError, ValueError):
            raise ImportContentError("content.import_id_invalid.v1") from None
        id_owner_id = (
            Article.objects.filter(pk=identity)
            .values_list("author_id", flat=True)
            .first()
        )
    title_owners = tuple(
        Article.objects.filter(working_revision__title=title)
        .order_by("author_id", "id")
        .values_list("author_id", flat=True)
    )
    return ImportConflictFacts(id_owner_id, title_owners)


def _section_by_name(name: object) -> UUID | None:
    if name is None or name == "":
        return None
    try:
        _, normalized = normalize_section_name(name)  # type: ignore[arg-type]
    except ValidationError:
        raise ImportContentError("content.import_section_invalid.v1") from None
    return (
        Section.objects.filter(normalized_name=normalized)
        .values_list("id", flat=True)
        .first()
    )


def _normalized_tag_names(values: object) -> tuple[tuple[str, str], ...]:
    if isinstance(values, (str, bytes)):
        raise ImportContentError("content.import_tags_invalid.v1")
    try:
        raw_values = tuple(values)  # type: ignore[arg-type]
    except TypeError:
        raise ImportContentError("content.import_tags_invalid.v1") from None
    normalized: dict[str, str] = {}
    for value in raw_values:
        try:
            display, key = normalize_tag_name(value)
        except ValidationError:
            raise ImportContentError("content.import_tags_invalid.v1") from None
        normalized.setdefault(key, display)
    if len(normalized) > 10:
        raise ImportContentError("content.import_tags_invalid.v1")
    return tuple((display, key) for key, display in normalized.items())


def _resolve_tag_names(
    normalized_names: tuple[tuple[str, str], ...],
) -> tuple[tuple[UUID, ...], tuple[str, ...]]:
    rows = {
        tag.normalized_name: tag
        for tag in Tag.objects.filter(
            normalized_name__in=[key for _, key in normalized_names],
            state__in=(Tag.State.PENDING, Tag.State.ACTIVE),
        ).order_by("created_at", "id")
    }
    tag_ids: list[UUID] = []
    proposed: list[str] = []
    for display, key in normalized_names:
        tag = rows.get(key)
        if tag is None:
            proposed.append(display)
        else:
            tag_ids.append(tag.id)
    return tuple(tag_ids), tuple(proposed)


def resolve_import_metadata(
    *, section_name: object, tag_names: object
) -> ImportMappingFacts:
    section_id = _section_by_name(section_name)
    tag_ids, proposed = _resolve_tag_names(_normalized_tag_names(tag_names))
    return ImportMappingFacts(section_id, tag_ids, proposed)


def validate_import_mapping(
    *, section_id: UUID | str | None, tag_ids: object, proposed_tag_names: object
) -> ImportMappingFacts:
    normalized_section = None
    if section_id is not None:
        try:
            normalized_section = UUID(str(section_id))
        except (TypeError, ValueError):
            raise ImportContentError("content.import_section_invalid.v1") from None
        if not Section.objects.filter(pk=normalized_section).exists():
            raise ImportContentError("content.import_section_invalid.v1")
    if isinstance(tag_ids, (str, bytes)):
        raise ImportContentError("content.import_tags_invalid.v1")
    try:
        normalized_ids = tuple(UUID(str(value)) for value in tag_ids)  # type: ignore[union-attr]
    except (TypeError, ValueError):
        raise ImportContentError("content.import_tags_invalid.v1") from None
    if len(normalized_ids) != len(set(normalized_ids)):
        raise ImportContentError("content.import_tags_invalid.v1")
    usable = {
        tag.id
        for tag in Tag.objects.filter(id__in=normalized_ids).only("id", "state")
        if tag.state in {Tag.State.ACTIVE, Tag.State.PENDING}
    }
    if usable != set(normalized_ids):
        raise ImportContentError("content.import_tag_unavailable.v1")
    resolved_ids, proposed = _resolve_tag_names(
        _normalized_tag_names(proposed_tag_names)
    )
    combined_ids = tuple(dict.fromkeys((*normalized_ids, *resolved_ids)))
    if len(combined_ids) + len(proposed) > 10:
        raise ImportContentError("content.import_tags_invalid.v1")
    return ImportMappingFacts(normalized_section, combined_ids, proposed)
