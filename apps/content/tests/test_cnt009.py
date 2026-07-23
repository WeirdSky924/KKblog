import threading
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from django.apps import apps
from django.db import close_old_connections
from PIL import Image

from apps.accounts.public import set_account_enabled
from apps.content.consumers.account_status import consume_account_status_event
from apps.content.models import Article, ArticleTombstone, AuthorContentMask
from apps.content.public import (
    ArticleSnapshot,
    ContentFormat,
    article_for_reader,
    create_article,
    create_section,
    delete_article,
    prepare_publication,
    publish_article,
    publish_scheduled_article,
    published_revision,
    restore_deleted_article,
    save_revision,
    schedule_article,
)
from apps.content.queries.access import ArticleNotFound
from apps.core.events import ConsumerOutcome, EventEnvelope
from apps.core.events.outbox import envelope_from_model
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock
from apps.media.public import (
    MediaAccessError,
    MediaPurpose,
    authorize_asset_read,
    stage_upload,
)
from apps.media.storage import FilesystemMediaStorage
from apps.operations.public import record_audit_entry

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


def _snapshot(section_id, body: str) -> ArticleSnapshot:
    return ArticleSnapshot(
        content_format=ContentFormat.MARKDOWN,
        title="作者状态文章",
        body=body,
        section_id=section_id,
    )


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 12), "#507d63").save(output, format="PNG")
    return output.getvalue()


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


def _schedule(author, article, now: datetime, scheduled_for: datetime):
    review = prepare_publication(
        actor_id=author.id,
        article_id=article.article_id,
        revision_id=article.revision_id,
        expected_row_version=article.row_version,
        clock=FrozenClock(now),
    )
    return schedule_article(
        actor_id=author.id,
        article_id=article.article_id,
        revision_id=article.revision_id,
        expected_row_version=article.row_version,
        review_token=review.token,
        scheduled_local=scheduled_for.astimezone(SHANGHAI).replace(tzinfo=None),
        trace_code=new_trace_code(),
        clock=FrozenClock(now),
    )


def _set_status(admin, author, *, enabled: bool):
    event_type = "account.enabled.v1" if enabled else "account.disabled.v1"
    set_account_enabled(
        actor_id=admin.id,
        account_id=author.id,
        enabled=enabled,
        audit_writer=record_audit_entry,
        **_context(),
    )
    outbox = apps.get_model("core", "OutboxEvent")
    return envelope_from_model(
        outbox.objects.filter(
            aggregate_id=str(author.id),
            event_type=event_type,
        ).latest("created_at")
    )


def _envelope(author_id, event_type: str, occurred_at: datetime) -> EventEnvelope:
    return EventEnvelope(
        event_id=new_ulid(),
        event_type=event_type,
        schema_version=1,
        occurred_at=occurred_at,
        actor_id=None,
        aggregate_type="account",
        aggregate_id=str(author_id),
        trace_code=new_trace_code(),
        payload={},
    )


def test_disable_masks_published_content_and_enable_only_removes_that_mask(
    monkeypatch,
) -> None:
    now = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
    admin = _account("mask-admin", administrator=True)
    author = _account("mask-author")
    section = create_section(actor_id=admin.id, name="作者遮罩", **_context())
    visible = create_article(
        actor_id=author.id,
        snapshot=_snapshot(section.section_id, "可见正文"),
        capacity_check=lambda: None,
    )
    independently_hidden = create_article(
        actor_id=author.id,
        snapshot=_snapshot(section.section_id, "管理员遮罩正文"),
        capacity_check=lambda: None,
    )
    _publish(author, visible, now)
    _publish(author, independently_hidden, now)
    assert article_for_reader(actor_id=None, article_id=visible.article_id)

    disabled = _set_status(admin, author, enabled=False)
    first = consume_account_status_event(disabled)
    duplicate = consume_account_status_event(disabled)

    assert first.outcome == ConsumerOutcome.PROCESSED
    assert duplicate.outcome == ConsumerOutcome.ALREADY_PROCESSED
    mask = AuthorContentMask.objects.get(author_id=author.id)
    assert mask.masked is True
    with pytest.raises(ArticleNotFound):
        article_for_reader(actor_id=None, article_id=visible.article_id)
    assert published_revision(visible.article_id) is None
    aggregate = Article.objects.get(pk=visible.article_id)
    assert aggregate.published_revision_id == visible.revision_id
    assert aggregate.published_revision.visibility == "PUBLIC"

    enabled = _set_status(admin, author, enabled=True)
    consume_account_status_event(enabled)
    mask.refresh_from_db()
    assert mask.masked is False
    assert article_for_reader(actor_id=None, article_id=visible.article_id)

    import apps.content.policies.article_access as access_policy

    monkeypatch.setattr(
        access_policy,
        "_reader_mask",
        lambda article_id: article_id == independently_hidden.article_id,
    )
    with pytest.raises(ArticleNotFound):
        article_for_reader(actor_id=None, article_id=independently_hidden.article_id)
    outbox = apps.get_model("core", "OutboxEvent")
    assert (
        outbox.objects.filter(
            aggregate_id=str(author.id),
            event_type="article.author_mask_changed.v1",
        ).count()
        == 2
    )


def test_enabled_account_stays_masked_until_enable_event_is_consumed(
    isolated_media_root: Path,
) -> None:
    now = datetime(2026, 7, 23, 11, 0, tzinfo=UTC)
    admin = _account("lag-admin", administrator=True)
    author = _account("lag-author")
    section = create_section(actor_id=admin.id, name="事件滞后", **_context())
    article = create_article(
        actor_id=author.id,
        snapshot=_snapshot(section.section_id, "初始正文"),
        capacity_check=lambda: None,
    )
    asset = stage_upload(
        owner_id=author.id,
        purpose=MediaPurpose.BODY,
        original_name="mask.png",
        declared_content_type="image/png",
        chunks=[_png()],
        storage=FilesystemMediaStorage(isolated_media_root),
        capacity_check=lambda: None,
        target_id=article.article_id,
    )
    saved = save_revision(
        actor_id=author.id,
        article_id=article.article_id,
        expected_row_version=article.row_version,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.MARKDOWN,
            title="遮罩媒体",
            body=f"![遮罩](media:{asset.id})",
            section_id=section.section_id,
            body_asset_ids=(asset.id,),
        ),
        capacity_check=lambda: None,
    )
    _publish(author, saved, now)
    disabled = _set_status(admin, author, enabled=False)
    consume_account_status_event(disabled)
    enabled = _set_status(admin, author, enabled=True)

    with pytest.raises(ArticleNotFound):
        article_for_reader(actor_id=None, article_id=article.article_id)
    with pytest.raises(MediaAccessError):
        authorize_asset_read(actor_id=None, asset_id=asset.id)

    consume_account_status_event(enabled)
    assert article_for_reader(actor_id=None, article_id=article.article_id)
    assert authorize_asset_read(actor_id=None, asset_id=asset.id).public_immutable
    media_asset = apps.get_model("media", "MediaAsset").objects.get(pk=asset.id)
    assert media_asset.state == "ACTIVE"
    assert media_asset.bindings.filter(target_id=saved.revision_id).exists()
    role_model = apps.get_model("accounts", "RoleAssignment")
    role_model.objects.filter(account=author, role="AUTHOR").delete()
    assert article_for_reader(actor_id=None, article_id=article.article_id)
    assert authorize_asset_read(actor_id=None, asset_id=asset.id).public_immutable


def test_disable_cancels_live_and_cooling_schedules_without_restoring_them() -> None:
    now = datetime.now(UTC) - timedelta(hours=2)
    admin = _account("schedule-mask-admin", administrator=True)
    author = _account("schedule-mask-author")
    section = create_section(actor_id=admin.id, name="禁用排期", **_context())
    live = create_article(
        actor_id=author.id,
        snapshot=_snapshot(section.section_id, "普通排期"),
        capacity_check=lambda: None,
    )
    cooling = create_article(
        actor_id=author.id,
        snapshot=_snapshot(section.section_id, "冷静期排期"),
        capacity_check=lambda: None,
    )
    _schedule(author, live, now, now + timedelta(days=2))
    _schedule(author, cooling, now, now + timedelta(days=2))
    cooling_row = Article.objects.get(pk=cooling.article_id)
    delete_article(
        actor_id=author.id,
        article_id=cooling.article_id,
        expected_row_version=cooling_row.row_version,
        administrative=False,
        clock=FrozenClock(now + timedelta(minutes=30)),
        **_context(),
    )

    disabled = _set_status(admin, author, enabled=False)
    consume_account_status_event(disabled)

    live_row = Article.objects.get(pk=live.article_id)
    cooling_row.refresh_from_db()
    tombstone = ArticleTombstone.objects.get(article_id=cooling.article_id)
    assert live_row.publication_state == Article.PublicationState.DRAFT
    assert live_row.scheduled_revision_id is None
    assert live_row.scheduled_for is None and live_row.scheduled_at is None
    assert cooling_row.publication_state == Article.PublicationState.DRAFT
    assert cooling_row.deleted_at is not None
    assert tombstone.original_publication_state == Article.PublicationState.DRAFT
    assert tombstone.original_scheduled_revision_id is None
    assert tombstone.original_scheduled_for is None
    assert tombstone.original_scheduled_at is None

    enabled = _set_status(admin, author, enabled=True)
    consume_account_status_event(enabled)
    cooling_row.refresh_from_db()
    restored = restore_deleted_article(
        actor_id=author.id,
        article_id=cooling.article_id,
        expected_row_version=cooling_row.row_version,
        clock=FrozenClock(now + timedelta(days=1)),
        **_context(),
    )
    assert restored.publication_state == Article.PublicationState.DRAFT
    live_row.refresh_from_db()
    cooling_row.refresh_from_db()
    assert live_row.publication_state == Article.PublicationState.DRAFT
    assert cooling_row.publication_state == Article.PublicationState.DRAFT
    assert cooling_row.scheduled_revision_id is None
    assert cooling_row.scheduled_for is None and cooling_row.scheduled_at is None


def test_out_of_order_events_keep_newer_mask_and_only_cancel_older_schedules() -> None:
    base = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
    admin = _account("order-admin", administrator=True)
    author = _account("order-author")
    section = create_section(actor_id=admin.id, name="事件顺序", **_context())
    old_article = create_article(
        actor_id=author.id,
        snapshot=_snapshot(section.section_id, "禁用前排期"),
        capacity_check=lambda: None,
    )
    _schedule(author, old_article, base, base + timedelta(days=10))
    disabled = _envelope(author.id, "account.disabled.v1", base + timedelta(hours=1))
    enabled = _envelope(author.id, "account.enabled.v1", base + timedelta(hours=2))

    consume_account_status_event(enabled, clock=FrozenClock(base + timedelta(hours=2)))
    new_article = create_article(
        actor_id=author.id,
        snapshot=_snapshot(section.section_id, "启用后排期"),
        capacity_check=lambda: None,
    )
    _schedule(
        author,
        new_article,
        base + timedelta(hours=3),
        base + timedelta(days=11),
    )
    processed = consume_account_status_event(
        disabled,
        clock=FrozenClock(base + timedelta(hours=4)),
    )
    duplicate = consume_account_status_event(
        disabled,
        clock=FrozenClock(base + timedelta(hours=4)),
    )

    assert processed.outcome == ConsumerOutcome.PROCESSED
    assert duplicate.outcome == ConsumerOutcome.ALREADY_PROCESSED
    old_row = Article.objects.get(pk=old_article.article_id)
    new_row = Article.objects.get(pk=new_article.article_id)
    mask = AuthorContentMask.objects.get(author_id=author.id)
    assert old_row.publication_state == Article.PublicationState.DRAFT
    assert old_row.scheduled_revision_id is None
    assert new_row.publication_state == Article.PublicationState.SCHEDULED
    assert new_row.scheduled_revision_id == new_article.revision_id
    assert mask.masked is False
    assert mask.last_event_id == enabled.event_id
    assert mask.last_event_type == "account.enabled.v1"


def test_due_publication_and_disable_consumer_converge_to_one_cancel() -> None:
    now = datetime.now(UTC)
    admin = _account("race-admin", administrator=True)
    author = _account("race-author")
    section = create_section(actor_id=admin.id, name="禁用竞态", **_context())
    article = create_article(
        actor_id=author.id,
        snapshot=_snapshot(section.section_id, "竞态排期"),
        capacity_check=lambda: None,
    )
    scheduled = _schedule(
        author,
        article,
        now - timedelta(minutes=2),
        now + timedelta(minutes=1),
    )
    disabled = _set_status(admin, author, enabled=False)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    errors: list[Exception] = []

    def consume() -> None:
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            result = consume_account_status_event(disabled)
            outcomes.append(result.outcome.value)
        except Exception as error:  # pragma: no cover - asserted below
            errors.append(error)
        finally:
            close_old_connections()

    def publish() -> None:
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            result = publish_scheduled_article(
                article_id=article.article_id,
                scheduled_revision_id=article.revision_id,
                clock=FrozenClock(scheduled.scheduled_for),
            )
            outcomes.append(result.outcome)
        except Exception as error:  # pragma: no cover - asserted below
            errors.append(error)
        finally:
            close_old_connections()

    workers = [threading.Thread(target=consume), threading.Thread(target=publish)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    assert errors == []
    assert "processed" in outcomes
    assert set(outcomes) <= {"processed", "cancelled_author", "stale"}
    aggregate = Article.objects.get(pk=article.article_id)
    assert aggregate.publication_state == Article.PublicationState.DRAFT
    assert aggregate.scheduled_revision_id is None
    assert aggregate.scheduled_for is None and aggregate.scheduled_at is None
    assert AuthorContentMask.objects.get(author_id=author.id).masked is True
    outbox = apps.get_model("core", "OutboxEvent")
    assert (
        outbox.objects.filter(
            aggregate_id=article.article_id,
            event_type="article.schedule_cancelled.v1",
        ).count()
        == 1
    )
