import threading
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from django.apps import apps
from django.db import close_old_connections

from apps.content.models import Article, ArticleEditGrant, ArticleRevision
from apps.content.public import (
    ArticleSnapshot,
    ContentCommandError,
    ContentFormat,
    EditConflictError,
    EditTokenError,
    PublicationCommandError,
    create_article,
    create_section,
    open_edit_session,
    prepare_publication,
    publish_article,
    resolve_edit_conflict,
    save_revision,
    save_revision_with_token,
)
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock

pytestmark = pytest.mark.django_db(transaction=True)


def _admin(label: str = "conflict-admin"):
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


def _snapshot(section_id, body: str) -> ArticleSnapshot:
    return ArticleSnapshot(
        content_format=ContentFormat.MARKDOWN,
        title="并发文章",
        body=body,
        section_id=section_id,
    )


def _published_setup():
    admin = _admin()
    section = create_section(
        actor_id=admin.id,
        name="并发分区",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    article = create_article(
        actor_id=admin.id,
        snapshot=_snapshot(section.section_id, "已发布基线"),
        capacity_check=lambda: None,
    )
    now = FrozenClock(datetime(2026, 7, 23, 12, 0, tzinfo=UTC))
    review = prepare_publication(
        actor_id=admin.id,
        article_id=article.article_id,
        revision_id=article.revision_id,
        expected_row_version=article.row_version,
        clock=now,
    )
    publish_article(
        actor_id=admin.id,
        article_id=article.article_id,
        revision_id=article.revision_id,
        expected_row_version=article.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
        clock=now,
    )
    return admin, section, article


def test_two_edit_tokens_from_same_baseline_have_one_save_winner() -> None:
    admin, section, article = _published_setup()
    first = open_edit_session(actor_id=admin.id, article_id=article.article_id)
    second = open_edit_session(actor_id=admin.id, article_id=article.article_id)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    conflicts = []

    def save(token: str, body: str) -> None:
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            save_revision_with_token(
                actor_id=admin.id,
                article_id=article.article_id,
                edit_token=token,
                snapshot=_snapshot(section.section_id, body),
                capacity_check=lambda: None,
            )
        except EditConflictError as error:
            outcomes.append("conflict")
            conflicts.append(error.conflict)
        else:
            outcomes.append("saved")
        finally:
            close_old_connections()

    workers = [
        threading.Thread(target=save, args=(first.token, "标签页一")),
        threading.Thread(target=save, args=(second.token, "标签页二")),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    aggregate = Article.objects.get(pk=article.article_id)
    assert sorted(outcomes) == ["conflict", "saved"]
    assert ArticleRevision.objects.filter(article_id=article.article_id).count() == 2
    assert aggregate.published_revision_id == article.revision_id
    assert ArticleEditGrant.objects.filter(state="CONFLICT").count() == 1
    assert conflicts[0].current.revision_id == aggregate.working_revision_id
    assert conflicts[0].baseline.revision_id == article.revision_id
    assert "body" not in repr(conflicts[0]).lower()
    assert "标签页" not in repr(conflicts[0])


def test_conflict_blocks_save_and_publish_until_baseline_is_selected() -> None:
    admin, section, article = _published_setup()
    stale = open_edit_session(actor_id=admin.id, article_id=article.article_id)
    save_revision(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=article.row_version,
        snapshot=_snapshot(section.section_id, "另一会话已保存"),
        capacity_check=lambda: None,
    )
    with pytest.raises(EditConflictError):
        save_revision_with_token(
            actor_id=admin.id,
            article_id=article.article_id,
            edit_token=stale.token,
            snapshot=_snapshot(section.section_id, "过期标签页"),
            capacity_check=lambda: None,
        )

    aggregate = Article.objects.get(pk=article.article_id)
    with pytest.raises(ContentCommandError) as captured:
        save_revision(
            actor_id=admin.id,
            article_id=article.article_id,
            expected_row_version=aggregate.row_version,
            snapshot=_snapshot(section.section_id, "绕过 token"),
            capacity_check=lambda: None,
        )
    assert captured.value.code == "content.edit_conflict_unresolved.v1"
    with pytest.raises(PublicationCommandError) as captured:
        prepare_publication(
            actor_id=admin.id,
            article_id=article.article_id,
            revision_id=aggregate.working_revision_id,
            expected_row_version=aggregate.row_version,
        )
    assert captured.value.code == "content.edit_conflict_unresolved.v1"

    resolved = resolve_edit_conflict(
        actor_id=admin.id,
        article_id=article.article_id,
        conflict_token=stale.token,
        selected_revision_id=article.revision_id,
    )
    saved = save_revision_with_token(
        actor_id=admin.id,
        article_id=article.article_id,
        edit_token=resolved.token,
        snapshot=_snapshot(section.section_id, "基于旧版继续"),
        capacity_check=lambda: None,
    )
    revision = ArticleRevision.objects.get(pk=saved.write.revision_id)
    assert revision.based_on_id == article.revision_id
    assert (
        Article.objects.get(pk=article.article_id).published_revision_id
        == article.revision_id
    )
    assert not ArticleEditGrant.objects.filter(state="CONFLICT").exists()


def test_edit_token_is_hashed_and_cannot_cross_actor_or_article() -> None:
    admin, section, article = _published_setup()
    other = _author("conflict-other")
    session = open_edit_session(actor_id=admin.id, article_id=article.article_id)
    grant = ArticleEditGrant.objects.get(pk=session.grant_id)
    assert session.token not in grant.token_digest

    for actor_id, token in (
        (other.id, session.token),
        (admin.id, session.token + "tampered"),
    ):
        with pytest.raises(EditTokenError):
            save_revision_with_token(
                actor_id=actor_id,
                article_id=article.article_id,
                edit_token=token,
                snapshot=_snapshot(section.section_id, "不应保存"),
                capacity_check=lambda: None,
            )
