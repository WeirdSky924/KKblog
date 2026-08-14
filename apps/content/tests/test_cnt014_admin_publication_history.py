from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.apps import apps

from apps.content.models import AdminArticleViewReceipt, Article, ArticlePublication
from apps.content.public import (
    ArticleNotFound,
    ArticleSnapshot,
    ContentFormat,
    ImportArticleCommand,
    ImportOperation,
    ImportPublicationStatus,
    Visibility,
    admin_published_revision_history,
    article_published_revision_for_admin,
    change_visibility,
    create_article,
    create_section,
    import_article_item,
    prepare_publication,
    publish_article,
    save_revision,
)
from apps.core.events.models import OutboxEvent
from apps.core.ids import new_ulid
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


def _snapshot(section_id, *, title: str, body: str) -> ArticleSnapshot:
    return ArticleSnapshot(
        content_format=ContentFormat.MARKDOWN,
        title=title,
        body=body,
        section_id=section_id,
    )


def _publish(author, article_id: str, revision_id: str, clock: FrozenClock) -> None:
    article = Article.objects.get(pk=article_id)
    review = prepare_publication(
        actor_id=author.id,
        article_id=article_id,
        revision_id=revision_id,
        expected_row_version=article.row_version,
        clock=clock,
    )
    publish_article(
        actor_id=author.id,
        article_id=article_id,
        revision_id=revision_id,
        expected_row_version=article.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
        clock=clock,
    )


def _save(author, article_id: str, section_id, *, title: str, body: str):
    article = Article.objects.get(pk=article_id)
    return save_revision(
        actor_id=author.id,
        article_id=article_id,
        expected_row_version=article.row_version,
        snapshot=_snapshot(section_id, title=title, body=body),
        capacity_check=lambda: None,
    )


def test_admin_history_only_contains_revisions_that_were_published() -> None:
    administrator = _account("history-admin", administrator=True)
    author = _account("history-author", author=True)
    section = create_section(
        actor_id=administrator.id,
        name=f"历史分区-{uuid4()}",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    first = create_article(
        actor_id=author.id,
        snapshot=_snapshot(
            section.section_id,
            title="第一版",
            body="| 项目 | 结果 |\n| --- | --- |\n| 第一版 | 已发布 |",
        ),
        capacity_check=lambda: None,
    )
    first_time = FrozenClock(datetime(2026, 8, 11, 2, 0, tzinfo=UTC))
    _publish(author, first.article_id, first.revision_id, first_time)

    skipped = _save(
        author,
        first.article_id,
        section.section_id,
        title="未发布草稿",
        body="这次保存从未发布。",
    )
    latest = _save(
        author,
        first.article_id,
        section.section_id,
        title="第二版",
        body="第二版正文",
    )
    second_time = FrozenClock(first_time.now() + timedelta(hours=2))
    _publish(author, first.article_id, latest.revision_id, second_time)

    history = admin_published_revision_history(
        actor_id=administrator.id,
        article_id=first.article_id,
    )
    assert [item.revision_id for item in history] == [
        latest.revision_id,
        first.revision_id,
    ]
    assert skipped.revision_id not in {item.revision_id for item in history}
    assert [item.title for item in history] == ["第二版", "第一版"]
    assert [item.published_at for item in history] == [
        second_time.now(),
        first_time.now(),
    ]
    assert history[0].is_current is True
    assert history[1].is_current is False
    assert ArticlePublication.objects.filter(article_id=first.article_id).count() == 2

    old_version = article_published_revision_for_admin(
        actor_id=administrator.id,
        article_id=first.article_id,
        revision_id=first.revision_id,
        trace_code=new_trace_code(),
    )
    assert old_version.title == "第一版"
    assert "<table" in (old_version.rendered_body_html or "")
    assert "第一版" in (old_version.rendered_body_html or "")
    assert (
        AdminArticleViewReceipt.objects.filter(
            administrator=administrator,
            author=author,
            article_id=first.article_id,
        ).count()
        == 1
    )
    assert (
        OutboxEvent.objects.filter(
            event_type="article.admin_viewed.v1",
            aggregate_id=first.article_id,
        ).count()
        == 1
    )


def test_admin_history_rejects_unpublished_revision_and_non_admin() -> None:
    administrator = _account("history-boundary-admin", administrator=True)
    author = _account("history-boundary-author", author=True)
    section = create_section(
        actor_id=administrator.id,
        name=f"边界分区-{uuid4()}",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    draft = create_article(
        actor_id=author.id,
        snapshot=_snapshot(
            section.section_id,
            title="发布后继续编辑",
            body="已发布正文",
        ),
        capacity_check=lambda: None,
    )
    _publish(
        author,
        draft.article_id,
        draft.revision_id,
        FrozenClock(datetime(2026, 8, 11, 4, 0, tzinfo=UTC)),
    )
    unpublished = _save(
        author,
        draft.article_id,
        section.section_id,
        title="未发布版本",
        body="不应进入发布历史",
    )

    with pytest.raises(ArticleNotFound):
        article_published_revision_for_admin(
            actor_id=administrator.id,
            article_id=draft.article_id,
            revision_id=unpublished.revision_id,
            trace_code=new_trace_code(),
        )
    with pytest.raises(PermissionError):
        admin_published_revision_history(
            actor_id=author.id,
            article_id=draft.article_id,
        )


def test_imported_publication_is_recorded_with_its_supplied_time() -> None:
    administrator = _account("history-import-admin", administrator=True)
    author = _account("history-import-author", author=True)
    section = create_section(
        actor_id=administrator.id,
        name=f"导入分区-{uuid4()}",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    article_id = new_ulid()
    published_at = datetime(2026, 8, 10, 9, 30, tzinfo=UTC)

    imported = import_article_item(
        actor_id=author.id,
        command=ImportArticleCommand(
            import_key=f"import:{new_ulid()}:{new_ulid()}",
            operation=ImportOperation.CREATE,
            article_id=article_id,
            title="导入发布版本",
            body_markdown="导入正文",
            section_id=section.section_id,
            publication_status=ImportPublicationStatus.PUBLISHED,
            published_at=published_at,
        ),
        trace_code=new_trace_code(),
        capacity_check=lambda: None,
        clock=FrozenClock(datetime(2026, 8, 11, 8, 0, tzinfo=UTC)),
    )

    publication = ArticlePublication.objects.get(article_id=article_id)
    assert publication.revision_id == imported.revision_id
    assert publication.published_at == published_at


def test_visibility_change_creates_a_new_published_history_version() -> None:
    administrator = _account("history-visibility-admin", administrator=True)
    author = _account("history-visibility-author", author=True)
    section = create_section(
        actor_id=administrator.id,
        name=f"可见性分区-{uuid4()}",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    article = create_article(
        actor_id=author.id,
        snapshot=_snapshot(
            section.section_id,
            title="可见性历史",
            body="公开正文",
        ),
        capacity_check=lambda: None,
    )
    first_time = FrozenClock(datetime(2026, 8, 11, 10, 0, tzinfo=UTC))
    _publish(author, article.article_id, article.revision_id, first_time)
    changed_at = FrozenClock(first_time.now() + timedelta(hours=1))

    changed = change_visibility(
        actor_id=author.id,
        article_id=article.article_id,
        visibility=Visibility.PRIVATE,
        trace_code=new_trace_code(),
        clock=changed_at,
    )

    history = admin_published_revision_history(
        actor_id=administrator.id,
        article_id=article.article_id,
    )
    assert [item.revision_id for item in history] == [
        changed.revision_id,
        article.revision_id,
    ]
    assert history[0].visibility == Visibility.PRIVATE
    assert history[0].published_at == changed_at.now()
