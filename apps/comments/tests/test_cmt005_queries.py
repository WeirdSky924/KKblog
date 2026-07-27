from dataclasses import dataclass, field
from datetime import timedelta
from uuid import uuid4

import pytest
from django.apps import apps
from django.utils import timezone

from apps.comments.models import Comment, DiscussionThread
from apps.comments.ports import CommentAuthorIdentity
from apps.comments.queries.threads import (
    CommentCursorError,
    CommentSort,
    public_comment_page,
    public_reply_page,
)
from apps.core.ids import new_ulid

pytestmark = pytest.mark.django_db(transaction=True)


@dataclass
class _Accounts:
    identities: dict = field(default_factory=dict)

    def public_identities(self, account_ids):
        return {
            account_id: self.identities[account_id]
            for account_id in account_ids
            if account_id in self.identities
        }


@dataclass
class _Media:
    images: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def bound_image_ids(self, comment_ids):
        return {
            comment_id: self.images.get(comment_id, ()) for comment_id in comment_ids
        }


def _account(label: str):
    model = apps.get_model("accounts", "Account")
    return model.objects.create_account(
        email=f"cmt005-{uuid4()}@kaj.test",
        password="Valid-password-1",
        nickname=label,
    )


def _thread(owner) -> DiscussionThread:
    return DiscussionThread.objects.create(
        target_type="ARTICLE",
        target_id=new_ulid(),
        owner=owner,
    )


def _comment(
    thread,
    author,
    *,
    created_at,
    parent=None,
    root=None,
    depth=0,
    reply_count=0,
    state=Comment.State.VISIBLE,
    visible_at=None,
    body="公开评论",
) -> Comment:
    comment_id = new_ulid()
    deleted = state == Comment.State.DELETED
    return Comment.objects.create(
        id=comment_id,
        thread=thread,
        parent=parent,
        root_id=comment_id if root is None else root.id,
        author=author,
        author_kind=Comment.AuthorKind.ACCOUNT,
        body="" if deleted else body,
        state=state,
        visible_at=visible_at or created_at,
        depth=depth,
        reply_count=reply_count,
        client_ip="192.0.2.50",
        deleted_by_kind=Comment.DeletedByKind.SELF if deleted else None,
        created_at=created_at,
    )


def _accounts(*accounts) -> _Accounts:
    return _Accounts(
        {
            account.id: CommentAuthorIdentity(
                account.id,
                account.nickname,
                f"/people/{account.id}/",
            )
            for account in accounts
        }
    )


def test_top_level_keyset_sorting_is_stable_across_concurrent_insert() -> None:
    owner = _account("排序作者")
    thread = _thread(owner)
    base = timezone.now() - timedelta(days=1)
    roots = [
        _comment(
            thread,
            owner,
            created_at=base + timedelta(seconds=index),
            reply_count=index % 4,
            body=f"根评论 {index:02d}",
        )
        for index in range(45)
    ]
    accounts = _accounts(owner)
    media = _Media()

    first = public_comment_page(
        thread_id=thread.id,
        can_view=True,
        sort=CommentSort.EARLIEST,
        account_policy=accounts,
        media_gateway=media,
    )
    assert tuple(item.id for item in first.items) == tuple(
        item.id for item in roots[:20]
    )
    assert first.next_cursor

    concurrent = _comment(
        thread,
        owner,
        created_at=timezone.now(),
        body="分页期间新增",
    )
    second = public_comment_page(
        thread_id=thread.id,
        can_view=True,
        sort=CommentSort.EARLIEST,
        cursor=first.next_cursor,
        account_policy=accounts,
        media_gateway=media,
    )
    third = public_comment_page(
        thread_id=thread.id,
        can_view=True,
        sort=CommentSort.EARLIEST,
        cursor=second.next_cursor,
        account_policy=accounts,
        media_gateway=media,
    )
    paged = (*first.items, *second.items, *third.items)
    assert tuple(item.id for item in paged) == tuple(item.id for item in roots)
    assert len({item.id for item in paged}) == 45
    assert concurrent.id not in {item.id for item in paged}
    assert third.next_cursor is None

    latest = public_comment_page(
        thread_id=thread.id,
        can_view=True,
        sort=CommentSort.LATEST,
        account_policy=accounts,
        media_gateway=media,
    )
    assert latest.items[0].id == concurrent.id
    assert tuple(item.id for item in latest.items[1:4]) == tuple(
        item.id for item in reversed(roots[-3:])
    )

    hottest = public_comment_page(
        thread_id=thread.id,
        can_view=True,
        sort=CommentSort.HOTTEST,
        account_policy=accounts,
        media_gateway=media,
    )
    expected = sorted(
        (*roots, concurrent),
        key=lambda item: (-item.reply_count, item.created_at, item.id),
    )[:20]
    assert tuple(item.id for item in hottest.items) == tuple(
        item.id for item in expected
    )

    with pytest.raises(CommentCursorError):
        public_comment_page(
            thread_id=thread.id,
            can_view=True,
            sort=CommentSort.LATEST,
            cursor=first.next_cursor,
            account_policy=accounts,
            media_gateway=media,
        )


def test_reply_chain_loads_ten_at_a_time_and_preserves_deleted_nodes() -> None:
    owner = _account("回复作者")
    thread = _thread(owner)
    base = timezone.now() - timedelta(hours=2)
    root = _comment(thread, owner, created_at=base, reply_count=27, body="根节点")
    replies = []
    parent = root
    for depth in range(1, 26):
        reply = _comment(
            thread,
            owner,
            created_at=base + timedelta(seconds=depth),
            parent=parent,
            root=root,
            depth=depth,
            state=(Comment.State.DELETED if depth == 13 else Comment.State.VISIBLE),
            body=f"回复 {depth}",
        )
        replies.append(reply)
        parent = reply
    _comment(
        thread,
        owner,
        created_at=timezone.now(),
        visible_at=timezone.now() + timedelta(minutes=10),
        parent=parent,
        root=root,
        depth=26,
        state=Comment.State.BUFFERED,
        body="仍在缓冲",
    )
    asset_id = new_ulid()
    accounts = _accounts(owner)
    media = _Media({replies[2].id: (asset_id,)})

    roots = public_comment_page(
        thread_id=thread.id,
        can_view=True,
        sort=CommentSort.EARLIEST,
        account_policy=accounts,
        media_gateway=media,
    )
    preview = roots.items[0].reply_page
    assert tuple(item.id for item in preview.items) == tuple(
        item.id for item in replies[:10]
    )
    assert preview.next_cursor
    assert preview.items[2].image_urls == (f"/_kaj/media/{asset_id}",)

    second = public_reply_page(
        thread_id=thread.id,
        can_view=True,
        root_id=root.id,
        cursor=preview.next_cursor,
        account_policy=accounts,
        media_gateway=media,
    )
    third = public_reply_page(
        thread_id=thread.id,
        can_view=True,
        root_id=root.id,
        cursor=second.next_cursor,
        account_policy=accounts,
        media_gateway=media,
    )
    assert tuple(item.id for item in second.items) == tuple(
        item.id for item in replies[10:20]
    )
    assert second.items[2].is_deleted is True
    assert second.items[2].body is None
    assert tuple(item.id for item in third.items) == tuple(
        item.id for item in replies[20:]
    )
    assert third.next_cursor is None
    assert max(item.visual_depth for item in (*second.items, *third.items)) == 4

    hidden = public_comment_page(
        thread_id=thread.id,
        can_view=False,
        sort=CommentSort.EARLIEST,
        account_policy=accounts,
        media_gateway=media,
    )
    assert hidden.items == ()
    assert hidden.next_cursor is None
