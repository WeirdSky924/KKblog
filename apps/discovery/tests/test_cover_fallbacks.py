from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.apps import apps
from PIL import Image

from apps.content.public import (
    ArticleCoverCandidate,
    ArticleSnapshot,
    ContentFormat,
    create_article,
    create_section,
    prepare_publication,
    publish_article,
    resolve_article_covers,
    search_visible_titles,
    visible_article_page,
)
from apps.core.events import EventEnvelope
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock
from apps.discovery.cache import consume_discovery_cache_event
from apps.discovery.models import Bookmark
from apps.discovery.queries import article_detail_page, bookmark_page, home_article_page
from apps.media.models import MediaPurpose
from apps.media.public import stage_upload
from apps.media.storage import FilesystemMediaStorage

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
        nickname=f"Cover{label}",
    )
    role_model.objects.create(account=account, role="AUTHOR")
    role_model.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _png(color: str) -> bytes:
    stream = BytesIO()
    Image.new("RGB", (48, 32), color).save(stream, format="PNG")
    return stream.getvalue()


def _asset(owner, media_root, *, purpose: str, color: str):
    return stage_upload(
        owner_id=owner.id,
        purpose=purpose,
        original_name="cover.png",
        declared_content_type="image/png",
        chunks=(_png(color),),
        storage=FilesystemMediaStorage(media_root),
        capacity_check=lambda: None,
        target_id=new_ulid() if purpose == MediaPurpose.COVER else None,
    )


def _publish(author, *, section_id, title: str, cover_asset_id=None):
    draft = create_article(
        actor_id=author.id,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.MARKDOWN,
            title=title,
            body="# 正文\n\n用于验证封面回退。",
            section_id=section_id,
            cover_asset_id=cover_asset_id,
        ),
        capacity_check=lambda: None,
    )
    clock = FrozenClock(datetime(2026, 8, 11, 8, 0, tzinfo=UTC))
    review = prepare_publication(
        actor_id=author.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        clock=clock,
    )
    publish_article(
        actor_id=author.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
        clock=clock,
    )
    return draft


def _identity(account):
    return SimpleNamespace(
        account_id=account.id,
        display_name=account.nickname,
        avatar_url=None,
        avatar_initial=account.nickname[0],
        profile_url=f"/people/{account.id}/",
    )


def test_shared_cover_resolver_enforces_article_section_global_priority(
    isolated_media_root,
) -> None:
    author = _account("priority")
    section_cover = _asset(
        author,
        isolated_media_root,
        purpose=MediaPurpose.SECTION_COVER,
        color="#287c70",
    )
    article_cover = _asset(
        author,
        isolated_media_root,
        purpose=MediaPurpose.COVER,
        color="#7e2637",
    )
    section = create_section(
        actor_id=author.id,
        name=f"封面优先级-{uuid4()}",
        default_cover_asset_id=section_cover.id,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    custom = _publish(
        author,
        section_id=section.section_id,
        title="文章封面优先",
        cover_asset_id=article_cover.id,
    )
    inherited = _publish(
        author,
        section_id=section.section_id,
        title="继承分区封面",
    )
    global_revision = new_ulid()
    missing_custom_revision = new_ulid()

    resolved = resolve_article_covers(
        (
            ArticleCoverCandidate(
                custom.revision_id, article_cover.id, section.section_id
            ),
            ArticleCoverCandidate(inherited.revision_id, None, section.section_id),
            ArticleCoverCandidate(global_revision, None, None),
            ArticleCoverCandidate(
                missing_custom_revision, new_ulid(), section.section_id
            ),
        )
    )

    assert (
        resolved[custom.revision_id].asset_id,
        resolved[custom.revision_id].source,
    ) == (
        article_cover.id,
        "article",
    )
    assert (
        resolved[inherited.revision_id].asset_id,
        resolved[inherited.revision_id].source,
    ) == (section_cover.id, "section")
    assert (resolved[global_revision].asset_id, resolved[global_revision].source) == (
        None,
        "global",
    )
    assert (
        resolved[missing_custom_revision].asset_id,
        resolved[missing_custom_revision].source,
    ) == (section_cover.id, "section")


def test_section_cover_is_shared_by_home_search_bookmarks_and_detail(
    isolated_media_root, monkeypatch
) -> None:
    author = _account("surfaces")
    identity = _identity(author)
    monkeypatch.setattr(
        "apps.discovery.profile_identity._provider",
        lambda account_id: identity if account_id == author.id else None,
    )
    monkeypatch.setattr(
        "apps.discovery.profile_identity._collection_provider",
        lambda account_ids: (identity,) if author.id in account_ids else (),
    )
    section_cover = _asset(
        author,
        isolated_media_root,
        purpose=MediaPurpose.SECTION_COVER,
        color="#287c70",
    )
    section = create_section(
        actor_id=author.id,
        name=f"共享封面-{uuid4()}",
        default_cover_asset_id=section_cover.id,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    article = _publish(
        author,
        section_id=section.section_id,
        title="三级回退共享查询",
    )
    expected_url = f"/_kaj/media/{section_cover.id}"

    visible = visible_article_page(actor_id=author.id)
    searched = search_visible_titles(actor_id=author.id, query="三级回退共享查询")
    home = home_article_page(actor_id=author.id)
    Bookmark.objects.create(account=author, article_id=article.article_id)
    bookmarks = bookmark_page(account_id=author.id)
    detail = article_detail_page(actor_id=author.id, article_id=article.article_id)

    assert visible.items[0].cover_asset_id == section_cover.id
    assert searched.items[0].cover_asset_id == section_cover.id
    assert home.items[0].cover_url == expected_url
    assert bookmarks.items[0].article.cover_url == expected_url
    assert detail.cover_url == expected_url
    assert detail.uses_default_cover is False


class _RecordingCache:
    def __init__(self) -> None:
        self.calls = []

    def invalidate(self, *, article_ids=(), lists=True) -> None:
        self.calls.append((tuple(article_ids), lists))


def test_section_change_invalidates_all_discovery_lists() -> None:
    now = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)
    envelope = EventEnvelope(
        event_id=new_ulid(),
        event_type="section.changed.v1",
        schema_version=1,
        occurred_at=now,
        actor_id=None,
        aggregate_type="section",
        aggregate_id=str(uuid4()),
        trace_code=new_trace_code(),
        payload={"action": "updated"},
    )
    cache = _RecordingCache()

    consume_discovery_cache_event(
        envelope,
        cache=cache,
        clock=FrozenClock(now),
    )

    assert cache.calls == [((), True)]
