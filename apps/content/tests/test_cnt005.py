from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.apps import apps

from apps.content.models import Article
from apps.content.public import (
    ArticleLoginRequired,
    ArticleNotFound,
    ArticleSnapshot,
    ContentCommandError,
    ContentFormat,
    Visibility,
    article_for_admin,
    article_for_author,
    article_for_reader,
    change_visibility,
    create_article,
    create_section,
    prepare_publication,
    publish_article,
    save_revision,
)
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str, *, author: bool = False, administrator: bool = False):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    if author or administrator:
        role_model.objects.create(account=account, role="AUTHOR")
    if administrator:
        role_model.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _context() -> dict[str, str]:
    return {"trace_code": new_trace_code(), "client_ip": "127.0.0.1"}


def _snapshot(section_id, visibility: Visibility, body: str = "正文"):
    return ArticleSnapshot(
        content_format=ContentFormat.MARKDOWN,
        title="可见性文章",
        body=body,
        section_id=section_id,
        visibility=visibility,
    )


def _published(author, section_id, visibility: Visibility, now: datetime):
    article = create_article(
        actor_id=author.id,
        snapshot=_snapshot(section_id, visibility),
        capacity_check=lambda: None,
    )
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
    return article


@pytest.mark.parametrize(
    ("visibility", "visitor", "user", "author"),
    [
        (Visibility.PUBLIC, "visible", "visible", "visible"),
        (Visibility.AUTHENTICATED, "login", "visible", "visible"),
        (Visibility.PRIVATE, "missing", "missing", "visible"),
    ],
)
def test_reader_visibility_matrix(
    visibility: Visibility,
    visitor: str,
    user: str,
    author: str,
) -> None:
    admin = _account(f"matrix-admin-{visibility}", administrator=True)
    owner = _account(f"matrix-owner-{visibility}", author=True)
    user_account = _account(f"matrix-user-{visibility}")
    section = create_section(actor_id=admin.id, name="矩阵分区", **_context())
    now = datetime(2026, 7, 23, 7, 0, tzinfo=UTC)
    article = _published(owner, section.section_id, visibility, now)

    def observe(actor_id):
        try:
            result = article_for_reader(
                actor_id=actor_id, article_id=article.article_id
            )
        except ArticleLoginRequired:
            return "login"
        except ArticleNotFound:
            return "missing"
        return "visible" if result.revision_id == article.revision_id else "wrong"

    assert observe(None) == visitor
    assert observe(user_account.id) == user
    assert observe(owner.id) == author
    admin_view = article_for_admin(
        actor_id=admin.id,
        article_id=article.article_id,
        revision="published",
        clock=FrozenClock(now),
        trace_code=new_trace_code(),
    )
    assert admin_view.revision_id == article.revision_id


def test_draft_and_cooling_period_are_uniform_not_found_for_readers() -> None:
    admin = _account("state-admin", administrator=True)
    owner = _account("state-owner", author=True)
    user = _account("state-user")
    section = create_section(actor_id=admin.id, name="状态分区", **_context())
    draft = create_article(
        actor_id=owner.id,
        snapshot=_snapshot(section.section_id, Visibility.PUBLIC),
        capacity_check=lambda: None,
    )
    for actor_id in (None, user.id):
        with pytest.raises(ArticleNotFound):
            article_for_reader(actor_id=actor_id, article_id=draft.article_id)

    published = _published(
        owner,
        section.section_id,
        Visibility.PUBLIC,
        datetime(2026, 7, 23, 8, 0, tzinfo=UTC),
    )
    aggregate = Article.objects.get(pk=published.article_id)
    aggregate.deleted_at = datetime(2026, 7, 23, 9, 0, tzinfo=UTC)
    aggregate.purge_after = aggregate.deleted_at + timedelta(days=7)
    aggregate.save(update_fields=("deleted_at", "purge_after", "updated_at"))
    for actor_id in (None, user.id):
        with pytest.raises(ArticleNotFound):
            article_for_reader(actor_id=actor_id, article_id=published.article_id)
    assert article_for_author(
        actor_id=owner.id, article_id=published.article_id
    ).deleted_at


def test_admin_view_notification_is_once_per_shanghai_day_and_admin_cannot_edit() -> (
    None
):
    admin = _account("view-admin", administrator=True)
    owner = _account("view-owner", author=True)
    section = create_section(actor_id=admin.id, name="管理查看", **_context())
    now = datetime(2026, 7, 23, 15, 30, tzinfo=UTC)
    article = _published(owner, section.section_id, Visibility.PRIVATE, now)

    for moment in (now, now + timedelta(hours=1), now + timedelta(hours=8)):
        article_for_admin(
            actor_id=admin.id,
            article_id=article.article_id,
            revision="working",
            clock=FrozenClock(moment),
            trace_code=new_trace_code(),
        )
    receipt_model = apps.get_model("content", "AdminArticleViewReceipt")
    outbox_model = apps.get_model("core", "OutboxEvent")
    assert receipt_model.objects.count() == 2
    assert (
        outbox_model.objects.filter(event_type="article.admin_viewed.v1").count() == 2
    )

    with pytest.raises(ContentCommandError) as captured:
        save_revision(
            actor_id=admin.id,
            article_id=article.article_id,
            expected_row_version=article.row_version,
            snapshot=_snapshot(section.section_id, Visibility.PRIVATE, "越权修改"),
            capacity_check=lambda: None,
        )
    assert captured.value.code == "content.article_not_editable.v1"


def test_visibility_change_republishes_old_reader_content_without_pending_edit() -> (
    None
):
    admin = _account("change-admin", administrator=True)
    owner = _account("change-owner", author=True)
    user = _account("change-user")
    section = create_section(actor_id=admin.id, name="即时可见性", **_context())
    first_time = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
    article = _published(owner, section.section_id, Visibility.PUBLIC, first_time)
    saved = save_revision(
        actor_id=owner.id,
        article_id=article.article_id,
        expected_row_version=article.row_version,
        snapshot=_snapshot(section.section_id, Visibility.PUBLIC, "尚未发布的新正文"),
        capacity_check=lambda: None,
    )

    changed = change_visibility(
        actor_id=owner.id,
        article_id=article.article_id,
        visibility=Visibility.PRIVATE,
        trace_code=new_trace_code(),
        clock=FrozenClock(first_time + timedelta(hours=1)),
    )
    aggregate = Article.objects.get(pk=article.article_id)
    assert aggregate.working_revision_id == saved.revision_id
    assert aggregate.published_revision_id == changed.revision_id
    assert aggregate.published_at == first_time
    assert changed.body_markdown == "正文"
    with pytest.raises(ArticleNotFound):
        article_for_reader(actor_id=user.id, article_id=article.article_id)
    assert (
        article_for_reader(
            actor_id=owner.id, article_id=article.article_id
        ).body_markdown
        == "正文"
    )

    event_model = apps.get_model("core", "OutboxEvent")
    event = event_model.objects.get(event_type="article.visibility_changed.v1")
    assert event.payload == {
        "revision_id": changed.revision_id,
        "from": "PUBLIC",
        "to": "PRIVATE",
    }
    assert "尚未发布" not in str(event.payload)

    with pytest.raises(ContentCommandError) as captured:
        change_visibility(
            actor_id=admin.id,
            article_id=article.article_id,
            visibility=Visibility.PUBLIC,
            trace_code=new_trace_code(),
            clock=FrozenClock(first_time + timedelta(hours=2)),
        )
    assert captured.value.code == "content.article_not_editable.v1"


def test_disabled_author_is_hidden_from_reader_but_admin_can_view() -> None:
    admin = _account("disabled-view-admin", administrator=True)
    owner = _account("disabled-view-owner", author=True)
    section = create_section(actor_id=admin.id, name="禁用作者", **_context())
    now = datetime(2026, 7, 23, 11, 0, tzinfo=UTC)
    article = _published(owner, section.section_id, Visibility.PUBLIC, now)
    owner.status = "DISABLED"
    owner.save(update_fields=("status", "updated_at"))

    with pytest.raises(ArticleNotFound):
        article_for_reader(actor_id=None, article_id=article.article_id)
    assert (
        article_for_admin(
            actor_id=admin.id,
            article_id=article.article_id,
            revision="published",
            clock=FrozenClock(now),
            trace_code=new_trace_code(),
        ).revision_id
        == article.revision_id
    )


def test_admin_reading_own_draft_uses_author_semantics_without_notification() -> None:
    admin = _account("own-view-admin", administrator=True)
    section = create_section(actor_id=admin.id, name="自己的草稿", **_context())
    article = create_article(
        actor_id=admin.id,
        snapshot=_snapshot(section.section_id, Visibility.PRIVATE),
        capacity_check=lambda: None,
    )
    view = article_for_admin(
        actor_id=admin.id,
        article_id=article.article_id,
        revision="working",
        clock=FrozenClock(datetime(2026, 7, 23, 12, 0, tzinfo=UTC)),
        trace_code=new_trace_code(),
    )
    receipt_model = apps.get_model("content", "AdminArticleViewReceipt")
    assert view.can_edit is True
    assert view.admin_read_only is False
    assert receipt_model.objects.count() == 0
