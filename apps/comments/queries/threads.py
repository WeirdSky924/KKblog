from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from django.core import signing
from django.db.models import F, Q, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

from apps.core.ids import normalize_ulid

from ..models import Comment
from ..policies.deletion import comment_deletion_mode
from ..ports import (
    CommentAccountPolicy,
    CommentAuthorPresentation,
    CommentMediaGateway,
    default_comment_account_policy,
    default_comment_media_gateway,
)

_CURSOR_SALT = "comments.thread-cursor.v1"
_TOP_LEVEL_BATCH_SIZE = 20
_REPLY_BATCH_SIZE = 10


class CommentSort(StrEnum):
    EARLIEST = "earliest"
    LATEST = "latest"
    HOTTEST = "hottest"


class CommentCursorError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PublicReplyPage:
    items: tuple["PublicCommentItem", ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class PublicCommentItem:
    id: str
    parent_id: str | None
    depth: int
    visual_depth: int
    author: CommentAuthorPresentation
    body: str | None
    is_deleted: bool
    created_at: datetime
    reply_count: int
    image_urls: tuple[str, ...]
    deletion_mode: str | None
    reply_page: PublicReplyPage | None = None


@dataclass(frozen=True, slots=True)
class PublicCommentPage:
    sort: CommentSort
    items: tuple[PublicCommentItem, ...]
    next_cursor: str | None


def _thread_id(value) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError):
        raise CommentCursorError("Invalid comment thread") from None


def _sort(value: CommentSort | str) -> CommentSort:
    try:
        return CommentSort(value)
    except (TypeError, ValueError):
        raise CommentCursorError("Invalid comment sort") from None


def _aware(value: object) -> datetime:
    if not isinstance(value, str):
        raise CommentCursorError("Invalid comment cursor")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise CommentCursorError("Invalid comment cursor") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CommentCursorError("Invalid comment cursor")
    return parsed


def _load_cursor(token: str, expected: dict[str, object]) -> dict[str, object]:
    if not isinstance(token, str) or not token or len(token) > 2048:
        raise CommentCursorError("Invalid comment cursor")
    try:
        payload = signing.loads(token, salt=_CURSOR_SALT)
    except signing.BadSignature:
        raise CommentCursorError("Invalid comment cursor") from None
    if not isinstance(payload, dict) or any(
        payload.get(key) != value for key, value in expected.items()
    ):
        raise CommentCursorError("Invalid comment cursor")
    return payload


def _dump_cursor(payload: dict[str, object]) -> str:
    return signing.dumps(payload, salt=_CURSOR_SALT, compress=True)


def _root_position(
    *, token: str | None, thread_id: str, sort: CommentSort
) -> tuple[datetime, datetime | None, str | None, int | None]:
    if token is None:
        return timezone.now(), None, None, None
    payload = _load_cursor(
        token,
        {"v": 1, "kind": "root", "thread_id": thread_id, "sort": sort.value},
    )
    if set(payload) != {
        "v",
        "kind",
        "thread_id",
        "sort",
        "snapshot_at",
        "created_at",
        "id",
        "reply_count",
    }:
        raise CommentCursorError("Invalid comment cursor")
    identity = normalize_ulid(payload["id"])
    reply_count = payload["reply_count"]
    if isinstance(reply_count, bool) or not isinstance(reply_count, int):
        raise CommentCursorError("Invalid comment cursor")
    return (
        _aware(payload["snapshot_at"]),
        _aware(payload["created_at"]),
        identity,
        reply_count,
    )


def _reply_position(
    *, token: str | None, thread_id: str, root_id: str
) -> tuple[datetime, datetime | None, str | None]:
    if token is None:
        return timezone.now(), None, None
    payload = _load_cursor(
        token,
        {"v": 1, "kind": "reply", "thread_id": thread_id, "root_id": root_id},
    )
    if set(payload) != {
        "v",
        "kind",
        "thread_id",
        "root_id",
        "snapshot_at",
        "created_at",
        "id",
    }:
        raise CommentCursorError("Invalid comment cursor")
    return (
        _aware(payload["snapshot_at"]),
        _aware(payload["created_at"]),
        normalize_ulid(payload["id"]),
    )


def _visible_rows(*, thread_id: str, snapshot: datetime):
    return Comment.objects.filter(
        thread_id=thread_id,
        state__in=(Comment.State.VISIBLE, Comment.State.DELETED),
        visible_at__lte=snapshot,
    )


def _present_rows(
    rows: tuple[Comment, ...],
    *,
    account_policy: CommentAccountPolicy,
    media_gateway: CommentMediaGateway,
    actor_id: UUID | None,
    thread_owner_id: UUID,
    is_administrator: bool,
) -> dict[str, PublicCommentItem]:
    if not rows:
        return {}
    account_ids = tuple(
        dict.fromkeys(
            row.author_id
            for row in rows
            if row.author_kind == Comment.AuthorKind.ACCOUNT and row.author_id
        )
    )
    identities = account_policy.public_identities(account_ids)
    image_ids = media_gateway.bound_image_ids(tuple(row.id for row in rows))
    result = {}
    for row in rows:
        if row.author_kind == Comment.AuthorKind.ANONYMOUS:
            author = CommentAuthorPresentation("访客", None)
        elif row.author_kind == Comment.AuthorKind.DELETED_ACCOUNT:
            author = CommentAuthorPresentation("该账号已注销", None)
        else:
            identity = identities.get(row.author_id)
            author = CommentAuthorPresentation(
                identity.display_name if identity else "账户用户",
                identity.profile_url if identity else None,
            )
        deleted = row.state == Comment.State.DELETED
        result[row.id] = PublicCommentItem(
            id=row.id,
            parent_id=row.parent_id,
            depth=row.depth,
            visual_depth=min(row.depth, 4),
            author=author,
            body=None if deleted else row.body,
            is_deleted=deleted,
            created_at=row.created_at,
            reply_count=row.reply_count,
            image_urls=(
                ()
                if deleted
                else tuple(
                    f"/_kaj/media/{asset_id}" for asset_id in image_ids.get(row.id, ())
                )
            ),
            deletion_mode=comment_deletion_mode(
                state=row.state,
                author_kind=row.author_kind,
                author_id=row.author_id,
                actor_id=actor_id,
                thread_owner_id=thread_owner_id,
                is_administrator=is_administrator,
            ),
        )
    return result


def _reply_cursor(
    *, thread_id: str, root_id: str, snapshot: datetime, row: Comment
) -> str:
    return _dump_cursor(
        {
            "v": 1,
            "kind": "reply",
            "thread_id": thread_id,
            "root_id": root_id,
            "snapshot_at": snapshot.isoformat(),
            "created_at": row.created_at.isoformat(),
            "id": row.id,
        }
    )


def _reply_previews(
    *, thread_id: str, root_ids: tuple[str, ...], snapshot: datetime
) -> dict[str, tuple[tuple[Comment, ...], str | None]]:
    if not root_ids:
        return {}
    rows = tuple(
        _visible_rows(thread_id=thread_id, snapshot=snapshot)
        .filter(root_id__in=root_ids, depth__gte=1)
        .annotate(
            batch_position=Window(
                expression=RowNumber(),
                partition_by=(F("root_id"),),
                order_by=(F("created_at").asc(), F("id").asc()),
            )
        )
        .filter(batch_position__lte=_REPLY_BATCH_SIZE + 1)
        .order_by("root_id", "created_at", "id")
    )
    grouped: dict[str, list[Comment]] = {root_id: [] for root_id in root_ids}
    for row in rows:
        grouped[row.root_id].append(row)
    return {
        root_id: (
            tuple(items[:_REPLY_BATCH_SIZE]),
            _reply_cursor(
                thread_id=thread_id,
                root_id=root_id,
                snapshot=snapshot,
                row=items[_REPLY_BATCH_SIZE - 1],
            )
            if len(items) > _REPLY_BATCH_SIZE
            else None,
        )
        for root_id, items in grouped.items()
    }


def _root_cursor(
    *, thread_id: str, sort: CommentSort, snapshot: datetime, row: Comment
) -> str:
    return _dump_cursor(
        {
            "v": 1,
            "kind": "root",
            "thread_id": thread_id,
            "sort": sort.value,
            "snapshot_at": snapshot.isoformat(),
            "created_at": row.created_at.isoformat(),
            "id": row.id,
            "reply_count": row.reply_count,
        }
    )


def public_comment_page(
    *,
    thread_id,
    can_view: bool,
    sort: CommentSort | str = CommentSort.EARLIEST,
    cursor: str | None = None,
    account_policy: CommentAccountPolicy | None = None,
    media_gateway: CommentMediaGateway | None = None,
    actor_id: UUID | None = None,
    thread_owner_id: UUID | None = None,
    is_administrator: bool = False,
) -> PublicCommentPage:
    identity = _thread_id(thread_id)
    ordering = _sort(sort)
    if not isinstance(can_view, bool):
        raise TypeError("can_view must be a boolean")
    if not can_view:
        return PublicCommentPage(ordering, (), None)
    if thread_owner_id is None:
        thread_owner_id = UUID(int=0)
    snapshot, created_at, comment_id, reply_count = _root_position(
        token=cursor,
        thread_id=identity,
        sort=ordering,
    )
    query = _visible_rows(thread_id=identity, snapshot=snapshot).filter(
        parent__isnull=True
    )
    if created_at is not None and comment_id is not None:
        if ordering == CommentSort.EARLIEST:
            query = query.filter(
                Q(created_at__gt=created_at)
                | Q(created_at=created_at, id__gt=comment_id)
            )
        elif ordering == CommentSort.LATEST:
            query = query.filter(
                Q(created_at__lt=created_at)
                | Q(created_at=created_at, id__lt=comment_id)
            )
        else:
            query = query.filter(
                Q(reply_count__lt=reply_count)
                | Q(reply_count=reply_count, created_at__gt=created_at)
                | Q(
                    reply_count=reply_count,
                    created_at=created_at,
                    id__gt=comment_id,
                )
            )
    order_by = {
        CommentSort.EARLIEST: ("created_at", "id"),
        CommentSort.LATEST: ("-created_at", "-id"),
        CommentSort.HOTTEST: ("-reply_count", "created_at", "id"),
    }[ordering]
    fetched = tuple(query.order_by(*order_by)[: _TOP_LEVEL_BATCH_SIZE + 1])
    rows = fetched[:_TOP_LEVEL_BATCH_SIZE]
    previews = _reply_previews(
        thread_id=identity,
        root_ids=tuple(row.id for row in rows),
        snapshot=snapshot,
    )
    preview_rows = tuple(
        reply for root_id in (row.id for row in rows) for reply in previews[root_id][0]
    )
    accounts = account_policy or default_comment_account_policy()
    media = media_gateway or default_comment_media_gateway()
    presented = _present_rows(
        (*rows, *preview_rows),
        account_policy=accounts,
        media_gateway=media,
        actor_id=actor_id,
        thread_owner_id=thread_owner_id,
        is_administrator=is_administrator,
    )
    items = tuple(
        replace(
            presented[row.id],
            reply_page=PublicReplyPage(
                tuple(presented[reply.id] for reply in previews[row.id][0]),
                previews[row.id][1],
            ),
        )
        for row in rows
    )
    next_cursor = (
        _root_cursor(
            thread_id=identity,
            sort=ordering,
            snapshot=snapshot,
            row=rows[-1],
        )
        if len(fetched) > _TOP_LEVEL_BATCH_SIZE
        else None
    )
    return PublicCommentPage(ordering, items, next_cursor)


def public_reply_page(
    *,
    thread_id,
    can_view: bool,
    root_id: str,
    cursor: str | None = None,
    account_policy: CommentAccountPolicy | None = None,
    media_gateway: CommentMediaGateway | None = None,
    actor_id: UUID | None = None,
    thread_owner_id: UUID | None = None,
    is_administrator: bool = False,
) -> PublicReplyPage:
    identity = _thread_id(thread_id)
    try:
        root = normalize_ulid(root_id)
    except (TypeError, ValueError):
        raise CommentCursorError("Invalid comment root") from None
    if not isinstance(can_view, bool):
        raise TypeError("can_view must be a boolean")
    if not can_view:
        return PublicReplyPage((), None)
    if thread_owner_id is None:
        thread_owner_id = UUID(int=0)
    snapshot, created_at, comment_id = _reply_position(
        token=cursor,
        thread_id=identity,
        root_id=root,
    )
    root_exists = (
        _visible_rows(thread_id=identity, snapshot=snapshot)
        .filter(
            pk=root,
            parent__isnull=True,
        )
        .exists()
    )
    if not root_exists:
        raise CommentCursorError("Comment root is unavailable")
    query = _visible_rows(thread_id=identity, snapshot=snapshot).filter(
        root_id=root,
        depth__gte=1,
    )
    if created_at is not None and comment_id is not None:
        query = query.filter(
            Q(created_at__gt=created_at) | Q(created_at=created_at, id__gt=comment_id)
        )
    fetched = tuple(query.order_by("created_at", "id")[: _REPLY_BATCH_SIZE + 1])
    rows = fetched[:_REPLY_BATCH_SIZE]
    presented = _present_rows(
        rows,
        account_policy=account_policy or default_comment_account_policy(),
        media_gateway=media_gateway or default_comment_media_gateway(),
        actor_id=actor_id,
        thread_owner_id=thread_owner_id,
        is_administrator=is_administrator,
    )
    next_cursor = (
        _reply_cursor(
            thread_id=identity,
            root_id=root,
            snapshot=snapshot,
            row=rows[-1],
        )
        if len(fetched) > _REPLY_BATCH_SIZE
        else None
    )
    return PublicReplyPage(
        tuple(presented[row.id] for row in rows),
        next_cursor,
    )
