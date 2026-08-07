from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.db import close_old_connections, transaction
from django.test import override_settings
from django.utils import timezone

from apps.comments.models import Comment, DiscussionThread
from apps.comments.services.publication import (
    CommentPublicationOutcome,
    due_buffered_comment_ids,
    publish_due_comment,
)
from apps.comments.tasks.publication import (
    dispatch_due_comments,
    publish_due_comment_task,
)
from apps.core.ids import new_ulid

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str):
    account_model = apps.get_model("accounts", "Account")
    return account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )


def _thread(owner) -> DiscussionThread:
    return DiscussionThread.objects.create(
        target_type="ARTICLE",
        target_id=new_ulid(),
        owner=owner,
    )


def _comment(
    thread: DiscussionThread,
    author,
    *,
    visible_at,
    state: str = Comment.State.BUFFERED,
    body: str = "等待公开",
) -> Comment:
    comment_id = new_ulid()
    deleted = state == Comment.State.DELETED
    return Comment.objects.create(
        id=comment_id,
        thread=thread,
        parent=None,
        root_id=comment_id,
        author=author,
        author_kind=Comment.AuthorKind.ACCOUNT,
        body="" if deleted else body,
        state=state,
        visible_at=visible_at,
        depth=0,
        reply_count=0,
        client_ip="192.0.2.40",
        deleted_by_kind=(Comment.DeletedByKind.OWNER if deleted else None),
        created_at=visible_at - timedelta(minutes=10),
    )


def test_due_publication_ignores_closure_and_skips_future_or_deleted() -> None:
    owner = _account("cmt004-owner")
    thread = _thread(owner)
    now = timezone.now()
    due = _comment(thread, owner, visible_at=now - timedelta(minutes=2))
    future = _comment(thread, owner, visible_at=now + timedelta(minutes=2))
    deleted = _comment(
        thread,
        owner,
        visible_at=now - timedelta(minutes=1),
        state=Comment.State.DELETED,
    )
    thread.comments_enabled = False
    thread.save(update_fields=("comments_enabled", "updated_at"))

    assert due_buffered_comment_ids(now=now, batch_size=10) == (due.id,)
    assert publish_due_comment(comment_id=due.id, now=now).outcome == (
        CommentPublicationOutcome.PUBLISHED
    )
    assert publish_due_comment(comment_id=due.id, now=now).outcome == (
        CommentPublicationOutcome.ALREADY_VISIBLE
    )
    assert publish_due_comment(comment_id=future.id, now=now).outcome == (
        CommentPublicationOutcome.NOT_DUE
    )
    assert publish_due_comment(comment_id=deleted.id, now=now).outcome == (
        CommentPublicationOutcome.DELETED
    )

    due.refresh_from_db()
    future.refresh_from_db()
    deleted.refresh_from_db()
    assert due.state == Comment.State.VISIBLE
    assert future.state == Comment.State.BUFFERED
    assert deleted.state == Comment.State.DELETED


def test_missed_tick_publishes_all_overdue_rows_in_bounded_batches() -> None:
    owner = _account("cmt004-missed")
    thread = _thread(owner)
    now = timezone.now()
    comments = [
        _comment(
            thread,
            owner,
            visible_at=now - timedelta(hours=3, minutes=index),
        )
        for index in range(3)
    ]

    first = due_buffered_comment_ids(now=now, batch_size=2)
    assert first == tuple(comment.id for comment in reversed(comments[1:]))
    for comment_id in first:
        assert publish_due_comment(comment_id=comment_id, now=now).outcome == (
            CommentPublicationOutcome.PUBLISHED
        )
    second = due_buffered_comment_ids(now=now, batch_size=2)
    assert second == (comments[0].id,)


def test_due_scan_uses_skip_locked() -> None:
    owner = _account("cmt004-skip-locked")
    thread = _thread(owner)
    now = timezone.now()
    first = _comment(thread, owner, visible_at=now - timedelta(minutes=2))
    second = _comment(thread, owner, visible_at=now - timedelta(minutes=1))

    def scan():
        close_old_connections()
        try:
            return due_buffered_comment_ids(now=now, batch_size=1)
        finally:
            close_old_connections()

    with transaction.atomic():
        Comment.objects.select_for_update().get(pk=first.id)
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(scan).result(timeout=5) == (second.id,)


def test_two_workers_publish_once_with_idempotent_outcome() -> None:
    owner = _account("cmt004-concurrent")
    thread = _thread(owner)
    now = timezone.now()
    comment = _comment(thread, owner, visible_at=now - timedelta(minutes=1))
    barrier = Barrier(2)

    def worker() -> str:
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            return publish_due_comment(comment_id=comment.id, now=now).outcome
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: worker(), range(2)))
    assert sorted(outcomes) == sorted(
        (
            CommentPublicationOutcome.PUBLISHED,
            CommentPublicationOutcome.ALREADY_VISIBLE,
        )
    )
    comment.refresh_from_db()
    assert comment.state == Comment.State.VISIBLE


def test_publication_task_is_tracked_and_idempotent() -> None:
    owner = _account("cmt004-task")
    thread = _thread(owner)
    comment = _comment(
        thread,
        owner,
        visible_at=timezone.now() - timedelta(minutes=1),
    )

    first = publish_due_comment_task.apply(
        args=(comment.id,), task_id=str(uuid4())
    ).get()
    duplicate = publish_due_comment_task.apply(
        args=(comment.id,), task_id=str(uuid4())
    ).get()
    task_run_model = apps.get_model("operations", "TaskRun")
    run = task_run_model.objects.get(task_name="apps.comments.publish_due_comment")

    assert first["status"] == "published"
    assert duplicate["status"] == "already_succeeded"
    assert run.idempotency_key == f"comment:{comment.id}:visible"
    assert run.status == "succeeded"
    assert run.attempt == 1


@override_settings(COMMENTS_PUBLICATION_BATCH_SIZE=2)
def test_dispatcher_queues_bounded_due_comments_and_has_beat_schedule(
    monkeypatch,
) -> None:
    owner = _account("cmt004-dispatch")
    thread = _thread(owner)
    now = timezone.now()
    comments = [
        _comment(
            thread,
            owner,
            visible_at=now - timedelta(minutes=3 - index),
        )
        for index in range(3)
    ]
    queued: list[str] = []
    monkeypatch.setattr(
        "apps.comments.tasks.publication.publish_due_comment_task.delay",
        queued.append,
    )

    result = dispatch_due_comments.apply(task_id=str(uuid4())).get()
    task_run_model = apps.get_model("operations", "TaskRun")
    run = task_run_model.objects.get(task_name="apps.comments.dispatch_due_comments")

    assert result["status"] == "queued"
    assert queued == [comments[0].id, comments[1].id]
    assert run.status == "succeeded"
    assert settings.CELERY_BEAT_SCHEDULE["comments-publish-due"] == {
        "task": "apps.comments.dispatch_due_comments",
        "schedule": 60.0,
    }
