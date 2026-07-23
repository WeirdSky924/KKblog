import threading
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from django.apps import apps
from django.conf import settings
from django.db import close_old_connections
from PIL import Image

from apps.content.models import Article, ArticleRevision, ArticleTombstone
from apps.content.public import (
    ArticleCommentPurgeResult,
    ArticleDeletionError,
    ArticlePurgeOutcome,
    ArticleSnapshot,
    ContentFormat,
    article_for_author,
    article_for_reader,
    create_article,
    create_section,
    delete_article,
    due_deleted_articles,
    prepare_publication,
    publish_article,
    publish_scheduled_article,
    purge_deleted_article,
    restore_deleted_article,
    save_revision,
    schedule_article,
)
from apps.content.queries.access import ArticleNotFound
from apps.content.tasks.deletion import purge_deleted_article_task
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock
from apps.media.public import (
    MediaPurpose,
    delete_pending_asset,
    stage_upload,
)
from apps.media.storage import FilesystemMediaStorage

pytestmark = pytest.mark.django_db(transaction=True)
SHANGHAI = ZoneInfo("Asia/Shanghai")


def _account(label: str, *, administrator: bool = False):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    role_model.objects.create(account=account, role="AUTHOR")
    if administrator:
        role_model.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _context() -> dict[str, str]:
    return {"trace_code": new_trace_code(), "client_ip": "127.0.0.1"}


def _snapshot(
    section_id,
    body: str = "删除正文",
    *,
    body_asset_ids: tuple[str, ...] = (),
) -> ArticleSnapshot:
    return ArticleSnapshot(
        content_format=ContentFormat.MARKDOWN,
        title="删除文章",
        body=body,
        section_id=section_id,
        body_asset_ids=body_asset_ids,
    )


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 12), "#3b82a0").save(output, format="PNG")
    return output.getvalue()


def _asset(owner, root: Path, article_id: str):
    return stage_upload(
        owner_id=owner.id,
        purpose=MediaPurpose.BODY,
        original_name="purge.png",
        declared_content_type="image/png",
        chunks=[_png()],
        storage=FilesystemMediaStorage(root),
        capacity_check=lambda: None,
        target_id=article_id,
    )


def _publish(author, article, now: datetime) -> None:
    review = prepare_publication(
        actor_id=author.id,
        article_id=article.article_id,
        revision_id=article.revision_id,
        expected_row_version=article.row_version,
        clock=FrozenClock(now),
    )
    publish_article(
        actor_id=author.id,
        article_id=article.article_id,
        revision_id=article.revision_id,
        expected_row_version=article.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
        clock=FrozenClock(now),
    )


def test_soft_delete_hides_then_restores_published_state_before_deadline() -> None:
    now = datetime(2026, 7, 23, 4, 0, tzinfo=UTC)
    admin = _account("delete-owner", administrator=True)
    section = create_section(actor_id=admin.id, name="删除分区", **_context())
    article = create_article(
        actor_id=admin.id,
        snapshot=_snapshot(section.section_id),
        capacity_check=lambda: None,
    )
    _publish(admin, article, now)
    before = Article.objects.get(pk=article.article_id)

    deleted = delete_article(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=before.row_version,
        administrative=False,
        clock=FrozenClock(now),
        **_context(),
    )

    assert deleted.deleted_at == now
    assert deleted.purge_after == now + timedelta(days=7)
    assert ArticleRevision.objects.filter(article_id=article.article_id).count() == 1
    with pytest.raises(ArticleNotFound):
        article_for_reader(actor_id=None, article_id=article.article_id)
    cooling = article_for_author(
        actor_id=admin.id,
        article_id=article.article_id,
        clock=FrozenClock(now + timedelta(days=6)),
    )
    assert cooling.can_edit is False
    tombstone = ArticleTombstone.objects.get(article_id=article.article_id)
    assert tombstone.original_published_revision_id == article.revision_id
    assert tombstone.purged_at is None

    restored = restore_deleted_article(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=deleted.row_version,
        clock=FrozenClock(now + timedelta(days=6)),
        **_context(),
    )

    aggregate = Article.objects.get(pk=article.article_id)
    assert restored.publication_state == Article.PublicationState.PUBLISHED
    assert aggregate.deleted_at is None and aggregate.purge_after is None
    assert aggregate.working_revision_id == article.revision_id
    assert aggregate.published_revision_id == article.revision_id
    assert not ArticleTombstone.objects.filter(article_id=article.article_id).exists()
    assert article_for_reader(actor_id=None, article_id=article.article_id).title == (
        "删除文章"
    )


def test_deadline_is_exclusive_and_deleted_schedule_is_not_cancelled() -> None:
    now = datetime(2026, 7, 23, 5, 0, tzinfo=UTC)
    admin = _account("delete-scheduled", administrator=True)
    section = create_section(actor_id=admin.id, name="删除排期", **_context())
    article = create_article(
        actor_id=admin.id,
        snapshot=_snapshot(section.section_id, "排期正文"),
        capacity_check=lambda: None,
    )
    review = prepare_publication(
        actor_id=admin.id,
        article_id=article.article_id,
        revision_id=article.revision_id,
        expected_row_version=article.row_version,
        clock=FrozenClock(now),
    )
    scheduled = schedule_article(
        actor_id=admin.id,
        article_id=article.article_id,
        revision_id=article.revision_id,
        expected_row_version=article.row_version,
        review_token=review.token,
        scheduled_local=(now + timedelta(days=1))
        .astimezone(SHANGHAI)
        .replace(tzinfo=None),
        trace_code=new_trace_code(),
        clock=FrozenClock(now),
    )
    aggregate = Article.objects.get(pk=article.article_id)
    deleted = delete_article(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=aggregate.row_version,
        administrative=False,
        clock=FrozenClock(now),
        **_context(),
    )

    execution = publish_scheduled_article(
        article_id=article.article_id,
        scheduled_revision_id=article.revision_id,
        clock=FrozenClock(scheduled.scheduled_for),
    )
    assert execution.outcome == "deferred_deleted"
    aggregate.refresh_from_db()
    assert aggregate.publication_state == Article.PublicationState.SCHEDULED
    assert aggregate.scheduled_revision_id == article.revision_id
    with pytest.raises(ArticleNotFound):
        article_for_author(
            actor_id=admin.id,
            article_id=article.article_id,
            clock=FrozenClock(deleted.purge_after),
        )
    with pytest.raises(ArticleDeletionError) as captured:
        restore_deleted_article(
            actor_id=admin.id,
            article_id=article.article_id,
            expected_row_version=deleted.row_version,
            clock=FrozenClock(deleted.purge_after),
            **_context(),
        )
    assert captured.value.code == "content.article_restore_expired.v1"
    assert due_deleted_articles(now=deleted.purge_after, batch_size=10) == (
        (article.article_id, deleted.purge_after),
    )


def test_only_admin_can_restore_another_authors_admin_deleted_article() -> None:
    now = datetime(2026, 7, 23, 6, 0, tzinfo=UTC)
    admin = _account("delete-admin", administrator=True)
    author = _account("delete-author")
    section = create_section(actor_id=admin.id, name="管理员删除", **_context())
    article = create_article(
        actor_id=author.id,
        snapshot=_snapshot(section.section_id),
        capacity_check=lambda: None,
    )
    deleted = delete_article(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=article.row_version,
        administrative=True,
        clock=FrozenClock(now),
        **_context(),
    )
    with pytest.raises(ArticleDeletionError) as captured:
        restore_deleted_article(
            actor_id=author.id,
            article_id=article.article_id,
            expected_row_version=deleted.row_version,
            clock=FrozenClock(now + timedelta(days=1)),
            **_context(),
        )
    assert captured.value.code == "content.article_restore_not_allowed.v1"

    restored = restore_deleted_article(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=deleted.row_version,
        clock=FrozenClock(now + timedelta(days=1)),
        **_context(),
    )
    assert restored.changed is True
    audit = apps.get_model("operations", "AuditEntry")
    assert list(
        audit.objects.filter(target_id=article.article_id)
        .order_by("created_at")
        .values_list("action", flat=True)
    ) == ["content.article.delete", "content.article.restore"]
    outbox = apps.get_model("core", "OutboxEvent")
    events = list(
        outbox.objects.filter(
            event_type__in=("article.deleted.v1", "article.restored.v1")
        ).order_by("occurred_at")
    )
    assert [event.event_type for event in events] == [
        "article.deleted.v1",
        "article.restored.v1",
    ]
    assert all(event.payload["recipient_id"] == str(author.id) for event in events)
    assert all(event.payload["administrative"] is True for event in events)


class _FailingDeleteStorage:
    def delete(self, storage_key: str) -> None:
        del storage_key
        raise OSError("injected file deletion failure")


def test_purge_commits_database_before_retryable_media_file_failure(
    isolated_media_root: Path,
) -> None:
    now = datetime(2026, 7, 23, 7, 0, tzinfo=UTC)
    admin = _account("purge-media", administrator=True)
    section = create_section(actor_id=admin.id, name="物理清理", **_context())
    article = create_article(
        actor_id=admin.id,
        snapshot=_snapshot(section.section_id),
        capacity_check=lambda: None,
    )
    asset = _asset(admin, isolated_media_root, article.article_id)
    saved = save_revision(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=article.row_version,
        snapshot=_snapshot(
            section.section_id,
            f"![待清理](media:{asset.id})",
            body_asset_ids=(asset.id,),
        ),
        capacity_check=lambda: None,
    )
    latest = save_revision(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=saved.row_version,
        snapshot=_snapshot(
            section.section_id,
            f"![共享待清理](media:{asset.id})",
            body_asset_ids=(asset.id,),
        ),
        capacity_check=lambda: None,
    )
    deleted = delete_article(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=latest.row_version,
        administrative=False,
        clock=FrozenClock(now),
        **_context(),
    )
    comment_calls: list[str] = []

    def purge_comments(article_id: str) -> ArticleCommentPurgeResult:
        comment_calls.append(article_id)
        return ArticleCommentPurgeResult(comment_count=3)

    result = purge_deleted_article(
        article_id=article.article_id,
        expected_purge_after=deleted.purge_after,
        clock=FrozenClock(deleted.purge_after),
        storage=_FailingDeleteStorage(),
        comment_purge=purge_comments,
    )

    assert result.outcome == ArticlePurgeOutcome.PURGED
    assert result.comment_count == 3
    assert result.asset_ids == (asset.id,)
    assert comment_calls == [article.article_id]
    assert not Article.objects.filter(pk=article.article_id).exists()
    assert not ArticleRevision.objects.filter(article_id=article.article_id).exists()
    binding = apps.get_model("media", "MediaBinding")
    media_asset = apps.get_model("media", "MediaAsset")
    assert not binding.objects.filter(asset_id=asset.id).exists()
    pending = media_asset.objects.get(pk=asset.id)
    assert pending.state == "DELETE_PENDING"
    file_path = isolated_media_root / pending.storage_key
    assert file_path.exists()
    tombstone = ArticleTombstone.objects.get(article_id=article.article_id)
    assert tombstone.purged_at == deleted.purge_after
    audit = apps.get_model("operations", "AuditEntry")
    assert audit.objects.filter(
        target_id=article.article_id,
        action="content.article.delete",
    ).exists()
    outbox = apps.get_model("core", "OutboxEvent")
    assert outbox.objects.filter(
        aggregate_id=article.article_id,
        event_type="article.purge_requested.v1",
    ).exists()

    cleanup = delete_pending_asset(
        asset_id=asset.id,
        storage=FilesystemMediaStorage(isolated_media_root),
    )
    assert cleanup.outcome.value == "deleted"
    assert not file_path.exists()


def test_comment_cleanup_failure_rolls_back_article_and_media(
    isolated_media_root: Path,
) -> None:
    now = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)
    admin = _account("purge-rollback", administrator=True)
    section = create_section(actor_id=admin.id, name="清理回滚", **_context())
    article = create_article(
        actor_id=admin.id,
        snapshot=_snapshot(section.section_id),
        capacity_check=lambda: None,
    )
    asset = _asset(admin, isolated_media_root, article.article_id)
    saved = save_revision(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=article.row_version,
        snapshot=_snapshot(
            section.section_id,
            f"![保留](media:{asset.id})",
            body_asset_ids=(asset.id,),
        ),
        capacity_check=lambda: None,
    )
    deleted = delete_article(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=saved.row_version,
        administrative=False,
        clock=FrozenClock(now),
        **_context(),
    )

    def fail_comments(article_id: str) -> ArticleCommentPurgeResult:
        del article_id
        raise RuntimeError("comment cleanup unavailable")

    with pytest.raises(RuntimeError, match="comment cleanup unavailable"):
        purge_deleted_article(
            article_id=article.article_id,
            expected_purge_after=deleted.purge_after,
            clock=FrozenClock(deleted.purge_after),
            storage=FilesystemMediaStorage(isolated_media_root),
            comment_purge=fail_comments,
        )

    assert Article.objects.filter(pk=article.article_id).exists()
    binding = apps.get_model("media", "MediaBinding")
    media_asset = apps.get_model("media", "MediaAsset")
    assert binding.objects.filter(
        target_id=saved.revision_id, asset_id=asset.id
    ).exists()
    assert media_asset.objects.get(pk=asset.id).state == "ACTIVE"
    assert (isolated_media_root / asset.storage_key).exists()
    assert ArticleTombstone.objects.get(article_id=article.article_id).purged_at is None


def test_two_workers_and_taskrun_purge_once() -> None:
    now = datetime(2026, 7, 23, 9, 0, tzinfo=UTC)
    admin = _account("purge-workers", administrator=True)
    section = create_section(actor_id=admin.id, name="双清理", **_context())
    article = create_article(
        actor_id=admin.id,
        snapshot=_snapshot(section.section_id),
        capacity_check=lambda: None,
    )
    deleted = delete_article(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=article.row_version,
        administrative=False,
        clock=FrozenClock(now),
        **_context(),
    )
    barrier = threading.Barrier(2)
    outcomes: list[ArticlePurgeOutcome] = []
    errors: list[Exception] = []

    def purge() -> None:
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            result = purge_deleted_article(
                article_id=article.article_id,
                expected_purge_after=deleted.purge_after,
                clock=FrozenClock(deleted.purge_after),
            )
            outcomes.append(result.outcome)
        except Exception as error:  # pragma: no cover - asserted below
            errors.append(error)
        finally:
            close_old_connections()

    workers = [threading.Thread(target=purge), threading.Thread(target=purge)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
    assert errors == []
    assert sorted(outcome.value for outcome in outcomes) == ["already_purged", "purged"]

    task_article = create_article(
        actor_id=admin.id,
        snapshot=_snapshot(section.section_id, "任务清理"),
        capacity_check=lambda: None,
    )
    task_now = datetime.now(UTC) - timedelta(days=8)
    task_deleted = delete_article(
        actor_id=admin.id,
        article_id=task_article.article_id,
        expected_row_version=task_article.row_version,
        administrative=False,
        clock=FrozenClock(task_now),
        **_context(),
    )
    deadline_us = int(task_deleted.purge_after.timestamp() * 1_000_000)
    response = purge_deleted_article_task.apply(
        args=(task_article.article_id, deadline_us),
        task_id=str(uuid4()),
    ).get()
    repeated = purge_deleted_article_task.apply(
        args=(task_article.article_id, deadline_us),
        task_id=str(uuid4()),
    ).get()

    assert response["status"] == "purged"
    assert repeated["status"] == "already_succeeded"
    task_run = apps.get_model("operations", "TaskRun")
    run = task_run.objects.get(
        idempotency_key=(f"article:{task_article.article_id}:purge:{deadline_us}")
    )
    assert run.status == "succeeded" and run.attempt == 1
    assert settings.CELERY_BEAT_SCHEDULE["content-purge-deleted"]["schedule"] == 3600.0
