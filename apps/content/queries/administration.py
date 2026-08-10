from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db.models import Case, Count, IntegerField, Q, When

from apps.accounts.public import is_administrator
from apps.core.ids import normalize_ulid

from ..models import Article, Section, Tag, TagAssociationHistory, TagRestoreConflict

ADMIN_ARTICLE_STATES = ("DRAFT", "SCHEDULED", "PUBLISHED", "DELETED")
ADMIN_TAG_STATES = tuple(Tag.State.values)


@dataclass(frozen=True, slots=True)
class AdminArticleItem:
    id: str
    author_id: UUID
    title: str
    publication_state: str
    visibility: str
    deleted_at: datetime | None
    purge_after: datetime | None
    published_at: datetime | None
    updated_at: datetime
    has_working_revision: bool
    has_published_revision: bool
    can_hide: bool
    can_delete: bool
    can_restore_deleted: bool


@dataclass(frozen=True, slots=True)
class AdminArticleTitle:
    id: str
    title: str


@dataclass(frozen=True, slots=True)
class AdminTagItem:
    id: UUID
    name: str
    state: str
    proposed_by_id: UUID | None
    reviewed_by_id: UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    current_article_count: int
    association_history_count: int
    pending_history_count: int
    open_conflict_count: int
    can_review: bool
    can_delete: bool
    can_restore: bool


@dataclass(frozen=True, slots=True)
class AdminTagAssociationHistoryItem:
    article_id: str
    article_title: str
    removed_at: datetime
    restored_at: datetime | None


@dataclass(frozen=True, slots=True)
class AdminTagRestoreConflictItem:
    article_id: str
    article_title: str
    reason: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AdminTagDetail:
    tag: AdminTagItem
    association_history: tuple[AdminTagAssociationHistoryItem, ...]
    open_conflicts: tuple[AdminTagRestoreConflictItem, ...]
    history_truncated: bool
    conflicts_truncated: bool


@dataclass(frozen=True, slots=True)
class AdminSectionItem:
    id: UUID
    name: str
    affected_article_count: int
    affected_revision_count: int
    created_at: datetime
    updated_at: datetime


def _keyword(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid administrator article query")
    normalized = value.strip()
    if len(normalized) > 100:
        raise ValueError("Invalid administrator article query")
    return normalized


def _item(article: Article) -> AdminArticleItem | None:
    revision = article.working_revision or article.published_revision
    if revision is None:
        return None
    active = article.deleted_at is None
    published = (
        active
        and article.publication_state == Article.PublicationState.PUBLISHED
        and article.published_revision_id is not None
    )
    return AdminArticleItem(
        id=article.id,
        author_id=article.author_id,
        title=revision.title,
        publication_state=article.publication_state,
        visibility=revision.visibility,
        deleted_at=article.deleted_at,
        purge_after=article.purge_after,
        published_at=article.latest_published_at,
        updated_at=article.updated_at,
        has_working_revision=article.working_revision_id is not None,
        has_published_revision=article.published_revision_id is not None,
        can_hide=published,
        can_delete=active,
        can_restore_deleted=not active,
    )


def admin_article_item(*, actor_id, article_id: str) -> AdminArticleItem:
    if not is_administrator(actor_id):
        raise PermissionError("Administrator article access denied")
    article = (
        Article.objects.select_related("working_revision", "published_revision")
        .filter(pk=article_id)
        .first()
    )
    item = _item(article) if article is not None else None
    if item is None:
        raise LookupError("Administrator article not found")
    return item


def admin_article_titles(
    *, actor_id, article_ids: tuple[str, ...]
) -> tuple[AdminArticleTitle, ...]:
    if not is_administrator(actor_id):
        raise PermissionError("Administrator article access denied")
    if not isinstance(article_ids, tuple) or len(article_ids) > 500:
        raise ValueError("Invalid administrator article identities")
    try:
        identities = tuple(
            dict.fromkeys(normalize_ulid(value) for value in article_ids)
        )
    except (TypeError, ValueError):
        raise ValueError("Invalid administrator article identities") from None
    rows = Article.objects.select_related(
        "working_revision", "published_revision"
    ).filter(pk__in=identities)
    return tuple(
        AdminArticleTitle(id=item.id, title=item.title)
        for article in rows
        if (item := _item(article)) is not None
    )


def admin_article_page(
    *, actor_id, query: str = "", state: str = "", limit: int = 200
) -> tuple[AdminArticleItem, ...]:
    if not is_administrator(actor_id):
        raise PermissionError("Administrator article access denied")
    keyword = _keyword(query)
    if state and state not in ADMIN_ARTICLE_STATES:
        raise ValueError("Invalid administrator article state")
    if isinstance(limit, bool) or not 1 <= limit <= 500:
        raise ValueError("Invalid administrator article limit")

    queryset = Article.objects.select_related(
        "working_revision",
        "published_revision",
    )
    if keyword:
        queryset = queryset.filter(
            Q(working_revision__title__icontains=keyword)
            | Q(published_revision__title__icontains=keyword)
            | Q(author__email__icontains=keyword)
            | Q(author__nickname__icontains=keyword)
        )
    if state == "DELETED":
        queryset = queryset.filter(deleted_at__isnull=False)
    elif state:
        queryset = queryset.filter(
            deleted_at__isnull=True,
            publication_state=state,
        )

    rows = queryset.order_by("-updated_at", "-id")[:limit]
    items = [item for article in rows if (item := _item(article)) is not None]
    return tuple(items)


def _require_classification_administrator(actor_id) -> None:
    if not is_administrator(actor_id):
        raise PermissionError("Administrator classification access denied")


def _classification_id(value, *, object_name: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise LookupError(f"Administrator {object_name} not found") from None


def _admin_tag_queryset():
    return Tag.objects.annotate(
        current_article_count=Count("current_articles", distinct=True),
        revision_article_count=Count(
            "revision_snapshots__revision__working_for_articles",
            distinct=True,
        ),
        association_history_count=Count("association_history", distinct=True),
        pending_history_count=Count(
            "association_history",
            filter=Q(association_history__restored_at__isnull=True),
            distinct=True,
        ),
        open_conflict_count=Count(
            "restore_conflicts",
            filter=Q(restore_conflicts__resolved_at__isnull=True),
            distinct=True,
        ),
    )


def _visible_admin_tag_queryset():
    return (
        _admin_tag_queryset()
        .filter(
            ~Q(state=Tag.State.PENDING)
            | Q(
                revision_snapshots__revision__published_for_articles__publication_state=(
                    Article.PublicationState.PUBLISHED
                ),
                revision_snapshots__revision__published_for_articles__deleted_at__isnull=True,
            )
        )
        .distinct()
    )


def _tag_item(tag: Tag) -> AdminTagItem:
    current_count = int(tag.current_article_count)
    history_count = int(tag.association_history_count)
    pending_count = int(tag.pending_history_count)
    conflict_count = int(tag.open_conflict_count)
    # Before delete/restore history exists, immutable revision facts can repair a
    # missing current projection without reviving an intentionally removed link.
    if tag.state in (Tag.State.PENDING, Tag.State.ACTIVE) and history_count == 0:
        current_count = max(current_count, int(tag.revision_article_count))
    return AdminTagItem(
        id=tag.id,
        name=tag.name,
        state=tag.state,
        proposed_by_id=tag.proposed_by_id,
        reviewed_by_id=tag.reviewed_by_id,
        reviewed_at=tag.reviewed_at,
        created_at=tag.created_at,
        updated_at=tag.updated_at,
        current_article_count=current_count,
        association_history_count=history_count,
        pending_history_count=pending_count,
        open_conflict_count=conflict_count,
        can_review=tag.state == Tag.State.PENDING,
        can_delete=tag.state == Tag.State.ACTIVE,
        can_restore=(
            tag.state == Tag.State.DELETED or pending_count > 0 or conflict_count > 0
        ),
    )


def admin_tag_page(
    *, actor_id, state: str = "", limit: int = 300
) -> tuple[AdminTagItem, ...]:
    _require_classification_administrator(actor_id)
    if state and state not in ADMIN_TAG_STATES:
        raise ValueError("Invalid administrator tag state")
    if isinstance(limit, bool) or not 1 <= limit <= 500:
        raise ValueError("Invalid administrator tag limit")
    rows = _visible_admin_tag_queryset()
    if state:
        rows = rows.filter(state=state)
    rows = rows.annotate(
        state_order=Case(
            When(state=Tag.State.PENDING, then=0),
            When(state=Tag.State.ACTIVE, then=1),
            When(state=Tag.State.DELETED, then=2),
            default=3,
            output_field=IntegerField(),
        )
    ).order_by("state_order", "normalized_name", "id")[:limit]
    return tuple(_tag_item(tag) for tag in rows)


def admin_pending_tag_review_count(*, actor_id) -> int:
    _require_classification_administrator(actor_id)
    return (
        Tag.objects.filter(
            state=Tag.State.PENDING,
            revision_snapshots__revision__published_for_articles__publication_state=(
                Article.PublicationState.PUBLISHED
            ),
            revision_snapshots__revision__published_for_articles__deleted_at__isnull=True,
        )
        .distinct()
        .count()
    )


def admin_tag_item(*, actor_id, tag_id) -> AdminTagItem:
    _require_classification_administrator(actor_id)
    identity = _classification_id(tag_id, object_name="tag")
    tag = _visible_admin_tag_queryset().filter(pk=identity).first()
    if tag is None:
        raise LookupError("Administrator tag not found")
    return _tag_item(tag)


def _article_titles(article_ids: tuple[str, ...]) -> dict[str, str]:
    rows = Article.objects.select_related(
        "working_revision", "published_revision"
    ).filter(pk__in=article_ids)
    return {
        item.id: item.title for article in rows if (item := _item(article)) is not None
    }


def admin_tag_detail(*, actor_id, tag_id, limit: int = 200) -> AdminTagDetail:
    tag = admin_tag_item(actor_id=actor_id, tag_id=tag_id)
    if isinstance(limit, bool) or not 1 <= limit <= 500:
        raise ValueError("Invalid administrator tag detail limit")
    histories = tuple(
        TagAssociationHistory.objects.filter(tag_id=tag.id).order_by(
            "-removed_at", "-id"
        )[: limit + 1]
    )
    conflicts = tuple(
        TagRestoreConflict.objects.filter(
            tag_id=tag.id, resolved_at__isnull=True
        ).order_by("-created_at", "-id")[: limit + 1]
    )
    visible_histories = histories[:limit]
    visible_conflicts = conflicts[:limit]
    titles = _article_titles(
        tuple(
            dict.fromkeys(
                item.article_id for item in (*visible_histories, *visible_conflicts)
            )
        )
    )
    return AdminTagDetail(
        tag=tag,
        association_history=tuple(
            AdminTagAssociationHistoryItem(
                article_id=item.article_id,
                article_title=titles.get(item.article_id, "文章已永久删除"),
                removed_at=item.removed_at,
                restored_at=item.restored_at,
            )
            for item in visible_histories
        ),
        open_conflicts=tuple(
            AdminTagRestoreConflictItem(
                article_id=item.article_id,
                article_title=titles.get(item.article_id, "文章已永久删除"),
                reason=item.reason,
                created_at=item.created_at,
            )
            for item in visible_conflicts
        ),
        history_truncated=len(histories) > limit,
        conflicts_truncated=len(conflicts) > limit,
    )


def _admin_section_queryset():
    return Section.objects.annotate(
        affected_article_count=Count("revisions__article_id", distinct=True),
        affected_revision_count=Count("revisions", distinct=True),
    )


def _section_item(section: Section) -> AdminSectionItem:
    return AdminSectionItem(
        id=section.id,
        name=section.name,
        affected_article_count=int(section.affected_article_count),
        affected_revision_count=int(section.affected_revision_count),
        created_at=section.created_at,
        updated_at=section.updated_at,
    )


def admin_section_page(*, actor_id, limit: int = 300) -> tuple[AdminSectionItem, ...]:
    _require_classification_administrator(actor_id)
    if isinstance(limit, bool) or not 1 <= limit <= 500:
        raise ValueError("Invalid administrator section limit")
    rows = _admin_section_queryset().order_by("normalized_name", "id")[:limit]
    return tuple(_section_item(section) for section in rows)


def admin_section_item(*, actor_id, section_id) -> AdminSectionItem:
    _require_classification_administrator(actor_id)
    identity = _classification_id(section_id, object_name="section")
    section = _admin_section_queryset().filter(pk=identity).first()
    if section is None:
        raise LookupError("Administrator section not found")
    return _section_item(section)


__all__ = [
    "ADMIN_ARTICLE_STATES",
    "ADMIN_TAG_STATES",
    "AdminArticleItem",
    "AdminArticleTitle",
    "AdminSectionItem",
    "AdminTagAssociationHistoryItem",
    "AdminTagDetail",
    "AdminTagItem",
    "AdminTagRestoreConflictItem",
    "admin_article_item",
    "admin_article_page",
    "admin_article_titles",
    "admin_section_item",
    "admin_section_page",
    "admin_pending_tag_review_count",
    "admin_tag_detail",
    "admin_tag_item",
    "admin_tag_page",
]
