from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.apps import apps

from apps.content.models import Article, PublicationReviewGrant
from apps.content.public import (
    ArticleSnapshot,
    ContentFormat,
    PublicationCommandError,
    create_article,
    create_section,
    prepare_publication,
    publish_article,
    published_revision,
    republish_saved_revision,
    save_revision,
)
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock

pytestmark = pytest.mark.django_db(transaction=True)


def _admin(label: str = "publish-admin"):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    role_model.objects.create(account=account, role="AUTHOR")
    role_model.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _author(label: str):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    role_model.objects.create(account=account, role="AUTHOR")
    return account


def _context() -> dict[str, str]:
    return {"trace_code": new_trace_code(), "client_ip": "127.0.0.1"}


def _snapshot(section_id, body: str = "正文") -> ArticleSnapshot:
    return ArticleSnapshot(
        content_format=ContentFormat.MARKDOWN,
        title="发布文章",
        body=body,
        section_id=section_id,
    )


def _article(admin, section_id, body: str = "正文"):
    return create_article(
        actor_id=admin.id,
        snapshot=_snapshot(section_id, body),
        capacity_check=lambda: None,
    )


def _section(admin):
    return create_section(actor_id=admin.id, name="发布分区", **_context())


def _review(admin, article, clock):
    return prepare_publication(
        actor_id=admin.id,
        article_id=article.article_id,
        revision_id=article.revision_id,
        expected_row_version=article.row_version,
        clock=clock,
    )


def _publish(admin, article, review, clock):
    return publish_article(
        actor_id=admin.id,
        article_id=article.article_id,
        revision_id=article.revision_id,
        expected_row_version=article.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
        clock=clock,
    )


def test_review_token_is_hashed_one_time_and_publishes_sanitized_revision() -> None:
    admin = _admin()
    section = _section(admin)
    article = _article(admin, section.section_id, "正文<script>alert(1)</script>")
    now = datetime(2026, 7, 23, 3, 0, tzinfo=UTC)
    clock = FrozenClock(now)

    review = _review(admin, article, clock)

    assert "<script" not in review.sanitized_html
    assert "正文" in review.sanitized_html
    grant = PublicationReviewGrant.objects.get(pk=review.grant_id)
    assert review.token not in grant.token_digest
    assert grant.expires_at == now + timedelta(minutes=15)

    published = _publish(admin, article, review, clock)
    aggregate = Article.objects.get(pk=article.article_id)
    grant.refresh_from_db()
    assert published.revision_id == article.revision_id
    assert aggregate.publication_state == Article.PublicationState.PUBLISHED
    assert aggregate.published_revision_id == article.revision_id
    assert aggregate.published_at == now
    assert aggregate.last_published_at == now
    assert grant.consumed_at == now
    assert published_revision(article.article_id).id == article.revision_id

    outbox_model = apps.get_model("core", "OutboxEvent")
    event = outbox_model.objects.get(event_type="article.published.v1")
    assert event.payload == {"revision_id": article.revision_id, "first": True}
    assert "正文" not in str(event.payload)

    with pytest.raises(PublicationCommandError) as captured:
        _publish(admin, article, review, clock)
    assert captured.value.code == "content.review_token_invalid.v1"


def test_review_token_expires_and_cannot_be_used_by_another_author() -> None:
    admin = _admin("token-admin")
    other = _author("token-other")
    section = _section(admin)
    article = _article(admin, section.section_id)
    now = datetime(2026, 7, 23, 3, 0, tzinfo=UTC)
    review = _review(admin, article, FrozenClock(now))

    with pytest.raises(PublicationCommandError) as captured:
        publish_article(
            actor_id=other.id,
            article_id=article.article_id,
            revision_id=article.revision_id,
            expected_row_version=article.row_version,
            review_token=review.token,
            trace_code=new_trace_code(),
            clock=FrozenClock(now),
        )
    assert captured.value.code == "content.article_not_editable.v1"

    with pytest.raises(PublicationCommandError) as captured:
        _publish(admin, article, review, FrozenClock(now + timedelta(minutes=16)))
    assert captured.value.code == "content.review_token_invalid.v1"


def test_editing_published_article_keeps_old_reader_revision_until_republish() -> None:
    admin = _admin("republish-admin")
    section = _section(admin)
    first = _article(admin, section.section_id, "第一版")
    first_time = datetime(2026, 7, 23, 4, 0, tzinfo=UTC)
    first_review = _review(admin, first, FrozenClock(first_time))
    _publish(admin, first, first_review, FrozenClock(first_time))

    saved = save_revision(
        actor_id=admin.id,
        article_id=first.article_id,
        expected_row_version=first.row_version,
        snapshot=_snapshot(section.section_id, "第二版"),
        capacity_check=lambda: None,
    )
    assert published_revision(first.article_id).body_markdown == "第一版"

    second_review = _review(admin, saved, FrozenClock(first_time + timedelta(hours=1)))
    _publish(
        admin,
        saved,
        second_review,
        FrozenClock(first_time + timedelta(hours=1)),
    )
    aggregate = Article.objects.get(pk=first.article_id)
    assert published_revision(first.article_id).body_markdown == "第二版"
    assert aggregate.published_at == first_time
    assert aggregate.last_published_at == first_time + timedelta(hours=1)


def test_preference_bridge_only_republishes_when_enabled_and_valid() -> None:
    admin = _admin("preference-admin")
    section = _section(admin)
    first = _article(admin, section.section_id, "第一版")
    now = datetime(2026, 7, 23, 5, 0, tzinfo=UTC)
    _publish(admin, first, _review(admin, first, FrozenClock(now)), FrozenClock(now))
    saved = save_revision(
        actor_id=admin.id,
        article_id=first.article_id,
        expected_row_version=first.row_version,
        snapshot=_snapshot(section.section_id, "自动重发版"),
        capacity_check=lambda: None,
    )

    skipped = republish_saved_revision(
        actor_id=admin.id,
        article_id=first.article_id,
        revision_id=saved.revision_id,
        expected_row_version=saved.row_version,
        auto_republish_enabled=False,
        trace_code=new_trace_code(),
        clock=FrozenClock(now + timedelta(hours=1)),
    )
    assert skipped.published is False
    assert published_revision(first.article_id).body_markdown == "第一版"

    completed = republish_saved_revision(
        actor_id=admin.id,
        article_id=first.article_id,
        revision_id=saved.revision_id,
        expected_row_version=saved.row_version,
        auto_republish_enabled=True,
        trace_code=new_trace_code(),
        clock=FrozenClock(now + timedelta(hours=1)),
    )
    assert completed.published is True
    assert published_revision(first.article_id).body_markdown == "自动重发版"


def test_publication_requires_section_at_review_and_execution() -> None:
    admin = _admin("section-check-admin")
    section = _section(admin)
    without_section = _article(admin, None)
    now = FrozenClock(datetime(2026, 7, 23, 6, 0, tzinfo=UTC))
    with pytest.raises(PublicationCommandError) as captured:
        _review(admin, without_section, now)
    assert captured.value.code == "content.section_required.v1"

    article = _article(admin, section.section_id)
    review = _review(admin, article, now)
    apps.get_model("content", "Section").objects.get(pk=section.section_id).delete()
    with pytest.raises(PublicationCommandError) as captured:
        _publish(admin, article, review, now)
    assert captured.value.code == "content.section_required.v1"
