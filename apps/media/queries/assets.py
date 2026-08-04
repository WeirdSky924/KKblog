from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db.models import Exists, OuterRef, Q

from apps.core.ids import normalize_ulid
from apps.media.models import (
    MediaAsset,
    MediaBinding,
    MediaPurpose,
    MediaState,
    MediaTargetType,
)


@dataclass(frozen=True, slots=True)
class ArticleBodyMediaItem:
    asset_id: str
    original_name: str
    size_bytes: int
    width: int
    height: int
    created_at: datetime
    deletable: bool


def _revision_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, tuple) or len(values) > 10_000:
        raise ValueError("Invalid article revision IDs")
    try:
        return tuple(dict.fromkeys(normalize_ulid(value) for value in values))
    except (TypeError, ValueError):
        raise ValueError("Invalid article revision IDs") from None


def owner_article_body_assets(
    *,
    owner_id: UUID,
    upload_scope: str,
    revision_ids: tuple[str, ...] = (),
) -> tuple[ArticleBodyMediaItem, ...]:
    if not isinstance(owner_id, UUID):
        raise ValueError("Invalid media owner ID")
    try:
        normalized_scope = normalize_ulid(upload_scope)
    except (TypeError, ValueError):
        raise ValueError("Invalid media upload scope") from None
    normalized_revisions = _revision_ids(revision_ids)
    scope_prefix = f"users/{owner_id}/articles/{normalized_scope}/body/"
    visible = Q(storage_key__startswith=scope_prefix)
    if normalized_revisions:
        visible |= Q(
            bindings__target_type=MediaTargetType.ARTICLE_REVISION,
            bindings__target_id__in=normalized_revisions,
        )
    has_binding = MediaBinding.objects.filter(asset_id=OuterRef("pk"))
    assets = (
        MediaAsset.objects.filter(
            owner_id=owner_id,
            purpose=MediaPurpose.BODY,
            state=MediaState.ACTIVE,
        )
        .filter(visible)
        .annotate(is_bound=Exists(has_binding))
        .distinct()
        .order_by("-created_at", "-id")
    )
    return tuple(
        ArticleBodyMediaItem(
            asset_id=asset.id,
            original_name=asset.original_name,
            size_bytes=asset.size_bytes,
            width=asset.width,
            height=asset.height,
            created_at=asset.created_at,
            deletable=not asset.is_bound,
        )
        for asset in assets
    )
