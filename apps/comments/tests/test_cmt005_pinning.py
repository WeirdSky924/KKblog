from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.comments.models import Comment, DiscussionThread
from apps.comments.queries import CommentSort, public_comment_page
from apps.comments.services import (
    CommentPinError,
    set_article_comment_pin,
    sync_article_thread,
)
from apps.content.public import (
    ArticleSnapshot,
    ContentFormat,
    create_article,
    create_section,
    prepare_publication,
    publish_article,
)
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str, *, roles: tuple[str, ...] = ()):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    for role in roles:
        role_model.objects.create(account=account, role=role)
    return account


def _thread(owner, *, target_type: str = "ARTICLE") -> DiscussionThread:
    return DiscussionThread.objects.create(
        target_type=target_type,
        target_id=new_ulid() if target_type == "ARTICLE" else "site",
        owner=owner,
    )


def _root(thread, author, *, body: str, age_minutes: int) -> Comment:
    created_at = timezone.now() - timedelta(minutes=age_minutes)
    comment_id = new_ulid()
    return Comment.objects.create(
        id=comment_id,
        thread=thread,
        parent=None,
        root_id=comment_id,
        author=author,
        author_kind=Comment.AuthorKind.ACCOUNT,
        body=body,
        state=Comment.State.VISIBLE,
        visible_at=created_at,
        depth=0,
        reply_count=0,
        client_ip="127.0.0.1",
        created_at=created_at,
    )


def _logged_in_client(account) -> Client:
    session_model = apps.get_model("accounts", "LoginSession")
    raw_token, _ = session_model.issue(account=account, remember=False)
    client = Client(REMOTE_ADDR="127.0.0.1")
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = raw_token
    return client


def _published_article_thread(owner) -> DiscussionThread:
    section = create_section(
        actor_id=owner.id,
        name=f"置顶测试分区-{uuid4()}",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    draft = create_article(
        actor_id=owner.id,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.MARKDOWN,
            title="评论置顶 HTTP 测试文章",
            body="正文",
            section_id=section.section_id,
        ),
        capacity_check=lambda: None,
    )
    clock = FrozenClock(datetime(2026, 8, 6, 12, 0, tzinfo=UTC))
    review = prepare_publication(
        actor_id=owner.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        clock=clock,
    )
    publish_article(
        actor_id=owner.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
        clock=clock,
    )
    return sync_article_thread(
        actor_id=owner.id,
        article_id=draft.article_id,
    )[0]


def test_author_or_admin_can_replace_and_remove_the_single_pin() -> None:
    owner = _account("pin-owner")
    member = _account("pin-member")
    admin = _account("pin-admin", roles=("AUTHOR", "ADMINISTRATOR"))
    thread = _thread(owner)
    first = _root(thread, member, body="第一条", age_minutes=2)
    second = _root(thread, member, body="第二条", age_minutes=1)

    with pytest.raises(CommentPinError) as denied:
        set_article_comment_pin(
            actor_id=member.id,
            comment_id=first.id,
            pinned=True,
        )
    assert denied.value.code == "comments.pin_forbidden.v1"

    initial = set_article_comment_pin(
        actor_id=owner.id,
        comment_id=first.id,
        pinned=True,
    )
    replaced = set_article_comment_pin(
        actor_id=admin.id,
        comment_id=second.id,
        pinned=True,
    )
    assert initial.changed is True
    assert replaced.changed is True
    pin_model = apps.get_model("comments", "CommentPin")
    assert pin_model.objects.get(thread=thread).comment_id == second.id

    removed = set_article_comment_pin(
        actor_id=owner.id,
        comment_id=second.id,
        pinned=False,
    )
    repeated = set_article_comment_pin(
        actor_id=owner.id,
        comment_id=second.id,
        pinned=False,
    )
    assert removed.changed is True
    assert repeated.changed is False
    assert not pin_model.objects.filter(thread=thread).exists()


def test_pin_rejects_replies_deleted_comments_and_guestbook() -> None:
    owner = _account("pin-shape-owner")
    member = _account("pin-shape-member")
    thread = _thread(owner)
    root = _root(thread, member, body="根评论", age_minutes=2)
    reply_created_at = timezone.now()
    reply = Comment.objects.create(
        id=new_ulid(),
        thread=thread,
        parent=root,
        root=root,
        author=member,
        author_kind=Comment.AuthorKind.ACCOUNT,
        body="回复",
        state=Comment.State.VISIBLE,
        visible_at=reply_created_at,
        depth=1,
        reply_count=0,
        client_ip="127.0.0.1",
        created_at=reply_created_at,
    )
    deleted = _root(thread, member, body="待删除", age_minutes=1)
    deleted.state = Comment.State.DELETED
    deleted.body = ""
    deleted.deleted_by_kind = Comment.DeletedByKind.OWNER
    deleted.save(update_fields=("state", "body", "deleted_by_kind", "updated_at"))
    guestbook = _root(
        _thread(owner, target_type="GUESTBOOK"),
        member,
        body="留言",
        age_minutes=1,
    )

    for comment in (reply, deleted, guestbook):
        with pytest.raises(CommentPinError) as invalid:
            set_article_comment_pin(
                actor_id=owner.id,
                comment_id=comment.id,
                pinned=True,
            )
        assert invalid.value.code == "comments.pin_invalid_target.v1"


@pytest.mark.parametrize("sort", tuple(CommentSort))
def test_pinned_comment_is_first_for_every_sort_without_duplicate(sort) -> None:
    owner = _account(f"pin-sort-owner-{sort}")
    member = _account(f"pin-sort-member-{sort}")
    thread = _thread(owner)
    comments = [
        _root(thread, member, body=f"评论 {index}", age_minutes=30 - index)
        for index in range(22)
    ]
    pinned = comments[10]
    set_article_comment_pin(
        actor_id=owner.id,
        comment_id=pinned.id,
        pinned=True,
    )

    first_page = public_comment_page(
        thread_id=thread.id,
        can_view=True,
        sort=sort,
        actor_id=owner.id,
        thread_owner_id=owner.id,
        can_pin=True,
    )
    assert first_page.items[0].id == pinned.id
    assert first_page.items[0].is_pinned is True
    assert first_page.items[0].can_pin is True
    assert len(first_page.items) == 20
    assert first_page.next_cursor is not None

    second_page = public_comment_page(
        thread_id=thread.id,
        can_view=True,
        sort=sort,
        cursor=first_page.next_cursor,
        actor_id=owner.id,
        thread_owner_id=owner.id,
        can_pin=True,
    )
    all_ids = [item.id for item in (*first_page.items, *second_page.items)]
    assert len(all_ids) == len(set(all_ids)) == 22
    assert all(not item.is_pinned for item in second_page.items)


def test_article_pin_http_reorders_the_comment_list() -> None:
    owner = _account("pin-http-owner", roles=("AUTHOR", "ADMINISTRATOR"))
    member = _account("pin-http-member")
    thread = _published_article_thread(owner)
    first = _root(thread, member, body="先发布", age_minutes=2)
    second = _root(thread, member, body="后发布", age_minutes=1)
    pin_url = reverse(
        "article:comment-pin",
        kwargs={"article_id": thread.target_id, "comment_id": second.id},
    )

    denied = _logged_in_client(member).post(
        pin_url,
        {"target_state": "pinned", "sort": "earliest"},
        HTTP_HX_REQUEST="true",
    )
    assert denied.status_code == 404

    response = _logged_in_client(owner).post(
        pin_url,
        {"target_state": "pinned", "sort": "earliest"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    html = response.content.decode()
    assert html.index(f'id="comment-{second.id}"') < html.index(
        f'id="comment-{first.id}"'
    )
    assert "已置顶" in html
    assert 'data-comment-pin-state="unpinned"' in html
