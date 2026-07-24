from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.comments.models import Comment, DiscussionThread
from apps.comments.targets import GUESTBOOK_TARGET_ID, registered_target_types
from apps.core.ids import new_ulid

pytestmark = pytest.mark.django_db(transaction=True)


def _account(email: str):
    account_model = django_apps.get_model("accounts", "Account")
    return account_model.objects.create_account(
        email=email,
        password="Valid-password-1",
    )


def _article_thread(owner) -> DiscussionThread:
    return DiscussionThread.objects.create(
        target_type=DiscussionThread.TargetType.ARTICLE,
        target_id=new_ulid(),
        owner=owner,
    )


def _top_level(
    *,
    thread: DiscussionThread,
    author,
    author_kind: str,
) -> Comment:
    comment_id = new_ulid()
    return Comment.objects.create(
        id=comment_id,
        thread=thread,
        parent=None,
        root_id=comment_id,
        author=author,
        author_kind=author_kind,
        body="第一条评论",
        state=Comment.State.BUFFERED,
        visible_at=timezone.now() + timedelta(minutes=10),
        depth=0,
        reply_count=0,
        client_ip="127.0.0.1",
    )


def test_thread_targets_are_closed_and_unique() -> None:
    owner = _account("owner@kaj.test")
    article_id = new_ulid()
    DiscussionThread.objects.create(
        target_type=DiscussionThread.TargetType.ARTICLE,
        target_id=article_id,
        owner=owner,
    )
    DiscussionThread.objects.create(
        target_type=DiscussionThread.TargetType.GUESTBOOK,
        target_id=GUESTBOOK_TARGET_ID,
        owner=owner,
    )
    assert registered_target_types() == ("ARTICLE", "GUESTBOOK")

    with pytest.raises(IntegrityError), transaction.atomic():
        DiscussionThread.objects.create(
            target_type=DiscussionThread.TargetType.ARTICLE,
            target_id=article_id,
            owner=owner,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        DiscussionThread.objects.create(
            target_type="OTHER",
            target_id="anything",
            owner=owner,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        DiscussionThread.objects.create(
            target_type=DiscussionThread.TargetType.GUESTBOOK,
            target_id="another-board",
            owner=owner,
        )


def test_comment_tree_rejects_cross_thread_parent_and_invalid_depth() -> None:
    owner = _account("tree-owner@kaj.test")
    first = _article_thread(owner)
    second = _article_thread(owner)
    root = _top_level(
        thread=first,
        author=owner,
        author_kind=Comment.AuthorKind.ACCOUNT,
    )
    reply = Comment.objects.create(
        id=new_ulid(),
        thread=first,
        parent=root,
        root=root,
        author=owner,
        author_kind=Comment.AuthorKind.ACCOUNT,
        body="合法回复",
        state=Comment.State.BUFFERED,
        visible_at=timezone.now() + timedelta(minutes=10),
        depth=1,
        reply_count=0,
        client_ip="127.0.0.1",
    )
    assert reply.root_id == root.id

    with pytest.raises(IntegrityError), transaction.atomic():
        Comment.objects.create(
            id=new_ulid(),
            thread=second,
            parent=root,
            root=root,
            author=owner,
            author_kind=Comment.AuthorKind.ACCOUNT,
            body="跨线程回复",
            state=Comment.State.BUFFERED,
            visible_at=timezone.now() + timedelta(minutes=10),
            depth=1,
            reply_count=0,
            client_ip="127.0.0.1",
        )

    with pytest.raises(IntegrityError), transaction.atomic():
        Comment.objects.create(
            id=new_ulid(),
            thread=first,
            parent=root,
            root=root,
            author=owner,
            author_kind=Comment.AuthorKind.ACCOUNT,
            body="错误深度",
            state=Comment.State.BUFFERED,
            visible_at=timezone.now() + timedelta(minutes=10),
            depth=3,
            reply_count=0,
            client_ip="127.0.0.1",
        )

    first_id = first.id
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM discussion_thread WHERE id = %s", [first_id])
    assert not Comment.objects.filter(pk__in=(root.id, reply.id)).exists()


def test_author_kind_shape_and_account_deletion_preserve_body() -> None:
    owner = _account("author-kind-owner@kaj.test")
    author = _account("commenter@kaj.test")
    thread = _article_thread(owner)
    comment = _top_level(
        thread=thread,
        author=author,
        author_kind=Comment.AuthorKind.ACCOUNT,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        _top_level(
            thread=thread,
            author=None,
            author_kind=Comment.AuthorKind.ACCOUNT,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        _top_level(
            thread=thread,
            author=owner,
            author_kind=Comment.AuthorKind.ANONYMOUS,
        )

    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM account WHERE id = %s", [author.id])
    comment.refresh_from_db()
    assert comment.author_id is None
    assert comment.author_kind == Comment.AuthorKind.DELETED_ACCOUNT
    assert comment.body == "第一条评论"
