from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from apps.core.ids import normalize_ulid
from apps.media.public import (
    MediaPurpose,
    MediaTargetType,
    target_binding_snapshots,
)

from .classification import section_cover_asset_ids


class ArticleCoverSource(StrEnum):
    ARTICLE = "article"
    SECTION = "section"
    GLOBAL = "global"


@dataclass(frozen=True, slots=True)
class ArticleCoverCandidate:
    revision_id: str
    article_cover_asset_id: str | None
    section_id: UUID | None


@dataclass(frozen=True, slots=True)
class ResolvedArticleCover:
    asset_id: str | None
    source: ArticleCoverSource


def _candidate(value: ArticleCoverCandidate) -> ArticleCoverCandidate:
    if not isinstance(value, ArticleCoverCandidate):
        raise ValueError("cover candidates must use ArticleCoverCandidate")
    try:
        revision_id = normalize_ulid(value.revision_id)
        article_cover_asset_id = (
            normalize_ulid(value.article_cover_asset_id)
            if value.article_cover_asset_id is not None
            else None
        )
        section_id = (
            UUID(str(value.section_id)) if value.section_id is not None else None
        )
    except (TypeError, ValueError):
        raise ValueError("cover candidate is invalid") from None
    return ArticleCoverCandidate(revision_id, article_cover_asset_id, section_id)


def resolve_article_covers(
    candidates: tuple[ArticleCoverCandidate, ...],
) -> dict[str, ResolvedArticleCover]:
    if not isinstance(candidates, tuple) or len(candidates) > 1000:
        raise ValueError("cover candidates must be a tuple of at most 1000 items")
    normalized = tuple(_candidate(item) for item in candidates)
    revision_ids = tuple(item.revision_id for item in normalized)
    if len(set(revision_ids)) != len(revision_ids):
        raise ValueError("cover candidates cannot repeat a revision")
    if not normalized:
        return {}

    article_bindings = target_binding_snapshots(
        target_type=MediaTargetType.ARTICLE_REVISION,
        target_ids=revision_ids,
    )
    section_ids = tuple(
        dict.fromkeys(str(item.section_id) for item in normalized if item.section_id)
    )
    section_covers = section_cover_asset_ids(section_ids) if section_ids else {}

    resolved: dict[str, ResolvedArticleCover] = {}
    for item in normalized:
        if item.article_cover_asset_id and any(
            binding.asset_id == item.article_cover_asset_id
            and binding.purpose == MediaPurpose.COVER
            and binding.state == "ACTIVE"
            and binding.slot == "cover"
            for binding in article_bindings[item.revision_id]
        ):
            resolved[item.revision_id] = ResolvedArticleCover(
                item.article_cover_asset_id,
                ArticleCoverSource.ARTICLE,
            )
            continue
        section_cover_id = (
            section_covers.get(str(item.section_id)) if item.section_id else None
        )
        if section_cover_id:
            resolved[item.revision_id] = ResolvedArticleCover(
                section_cover_id,
                ArticleCoverSource.SECTION,
            )
            continue
        resolved[item.revision_id] = ResolvedArticleCover(
            None,
            ArticleCoverSource.GLOBAL,
        )
    return resolved


__all__ = [
    "ArticleCoverCandidate",
    "ArticleCoverSource",
    "ResolvedArticleCover",
    "resolve_article_covers",
]
