import threading
from uuid import uuid4

import pytest
from django.apps import apps
from django.db import IntegrityError, close_old_connections, transaction

from apps.content.models import Article, Tag
from apps.content.public import (
    ArticleSnapshot,
    ContentCommandError,
    ContentFormat,
    TagCommandError,
    active_tag,
    create_article,
    create_tag,
    delete_tag,
    propose_tag,
    restore_tag,
    review_tag,
    save_revision,
    tags_for_article,
)
from apps.core.observability.trace import new_trace_code

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


def _snapshot(*, tag_ids=(), body="正文") -> ArticleSnapshot:
    return ArticleSnapshot(
        content_format=ContentFormat.MARKDOWN,
        title="标签文章",
        body=body,
        tag_ids=tuple(tag_ids),
    )


def _article(author, *, tag_ids=()):
    return create_article(
        actor_id=author.id,
        snapshot=_snapshot(tag_ids=tag_ids),
        capacity_check=lambda: None,
    )


def _publish_for_tag_review(article) -> None:
    Article.objects.filter(pk=article.article_id).update(
        publication_state=Article.PublicationState.PUBLISHED,
        published_revision_id=article.revision_id,
    )


def test_author_tag_proposals_are_casefold_unique_under_concurrency() -> None:
    first = _account("tag-author-one", author=True)
    second = _account("tag-author-two", author=True)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def propose(actor_id, name: str) -> None:
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            outcomes.append(str(propose_tag(actor_id=actor_id, name=name).tag_id))
        finally:
            close_old_connections()

    workers = [
        threading.Thread(target=propose, args=(first.id, "Straße")),
        threading.Thread(target=propose, args=(second.id, "STRASSE")),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    assert len(set(outcomes)) == 1
    tag = Tag.objects.get()
    assert tag.normalized_name == "strasse"
    assert tag.state == Tag.State.PENDING

    first_article = _article(first, tag_ids=(tag.id,))
    second_article = _article(second, tag_ids=(tag.id,))
    _publish_for_tag_review(first_article)
    admin = _account("shared-tag-admin", administrator=True)
    review_tag(
        actor_id=admin.id,
        tag_id=tag.id,
        approved=False,
        **_context(),
    )
    assert tags_for_article(first_article.article_id) == ()
    assert tags_for_article(second_article.article_id) == ()
    outbox_model = apps.get_model("core", "OutboxEvent")
    recipients = set(
        outbox_model.objects.filter(event_type="tag.reviewed.v1").values_list(
            "payload__recipient_id", flat=True
        )
    )
    assert recipients == {str(first.id), str(second.id)}


def test_pending_tag_is_visible_and_rejection_removes_current_projection() -> None:
    admin = _account("tag-review-admin", administrator=True)
    author = _account("tag-review-author", author=True)
    proposed = propose_tag(actor_id=author.id, name="待审核")
    article = _article(author, tag_ids=(proposed.tag_id,))
    _publish_for_tag_review(article)

    assert [
        (item.name, item.state) for item in tags_for_article(article.article_id)
    ] == [("待审核", Tag.State.PENDING)]
    with pytest.raises(TagCommandError) as captured:
        review_tag(
            actor_id=author.id,
            tag_id=proposed.tag_id,
            approved=False,
            **_context(),
        )
    assert captured.value.code == "content.tag_admin_required.v1"
    rejected = review_tag(
        actor_id=admin.id,
        tag_id=proposed.tag_id,
        approved=False,
        **_context(),
    )

    assert rejected.state == Tag.State.REJECTED
    assert tags_for_article(article.article_id) == ()
    revision_tag = apps.get_model("content", "RevisionTag")
    assert revision_tag.objects.filter(revision_id=article.revision_id).count() == 1
    outbox_model = apps.get_model("core", "OutboxEvent")
    event = outbox_model.objects.get(event_type="tag.reviewed.v1")
    assert event.payload["outcome"] == "rejected"
    assert event.payload["recipient_id"] == str(author.id)

    next_author = _account("tag-review-next-author", author=True)
    reproposed = propose_tag(actor_id=next_author.id, name="待审核")
    assert reproposed.tag_id == proposed.tag_id
    assert Tag.objects.filter(normalized_name="待审核").count() == 1
    tag = Tag.objects.get(pk=proposed.tag_id)
    assert tag.state == Tag.State.PENDING
    assert tag.proposed_by_id == next_author.id
    assert tag.reviewed_by_id is None
    assert tag.reviewed_at is None

    reproposed_article = _article(next_author, tag_ids=(reproposed.tag_id,))
    _publish_for_tag_review(reproposed_article)
    reapproved = review_tag(
        actor_id=admin.id,
        tag_id=reproposed.tag_id,
        approved=True,
        **_context(),
    )
    assert reapproved.tag_id == proposed.tag_id
    assert reapproved.state == Tag.State.ACTIVE
    audit_model = apps.get_model("operations", "AuditEntry")
    review_history = list(
        audit_model.objects.filter(
            action="content.tag.review",
            target_type="tag",
            target_id=str(proposed.tag_id),
        )
        .order_by("created_at", "id")
        .values_list("after_safe", flat=True)
    )
    assert [item["outcome"] for item in review_history] == ["rejected", "approved"]

    pending_approval = propose_tag(actor_id=author.id, name="可通过")
    approved_article = _article(author, tag_ids=(pending_approval.tag_id,))
    _publish_for_tag_review(approved_article)
    approved = review_tag(
        actor_id=admin.id,
        tag_id=pending_approval.tag_id,
        approved=True,
        **_context(),
    )
    assert approved.state == Tag.State.ACTIVE
    assert tags_for_article(approved_article.article_id)[0].state == Tag.State.ACTIVE


def test_article_tag_limit_is_serialized_for_two_saves() -> None:
    admin = _account("tag-limit-admin", administrator=True)
    tags = [
        create_tag(actor_id=admin.id, name=f"标签{index}", **_context())
        for index in range(11)
    ]
    article = _article(admin, tag_ids=[item.tag_id for item in tags[:9]])
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def save(extra_index: int) -> None:
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            save_revision(
                actor_id=admin.id,
                article_id=article.article_id,
                expected_row_version=article.row_version,
                snapshot=_snapshot(
                    tag_ids=[item.tag_id for item in tags[:9]]
                    + [tags[extra_index].tag_id],
                    body=f"并发版本 {extra_index}",
                ),
                capacity_check=lambda: None,
            )
        except ContentCommandError as error:
            outcomes.append(error.code)
        else:
            outcomes.append("saved")
        finally:
            close_old_connections()

    workers = [
        threading.Thread(target=save, args=(9,)),
        threading.Thread(target=save, args=(10,)),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    assert sorted(outcomes) == ["content.edit_conflict.v1", "saved"]
    article_tag = apps.get_model("content", "ArticleTag")
    assert article_tag.objects.filter(article_id=article.article_id).count() == 10
    current_ids = set(
        article_tag.objects.filter(article_id=article.article_id).values_list(
            "tag_id", flat=True
        )
    )
    missing_id = next(item.tag_id for item in tags if item.tag_id not in current_ids)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            article_tag.objects.create(
                article_id=article.article_id,
                tag_id=missing_id,
            )


def test_delete_restore_records_overflow_conflict_then_recovers() -> None:
    admin = _account("tag-restore-admin", administrator=True)
    tags = [
        create_tag(actor_id=admin.id, name=f"恢复{index}", **_context())
        for index in range(11)
    ]
    article = _article(admin, tag_ids=[item.tag_id for item in tags[:10]])
    deleted = delete_tag(actor_id=admin.id, tag_id=tags[0].tag_id, **_context())
    assert deleted.affected_article_count == 1
    assert active_tag(tags[0].tag_id) is None
    assert len(tags_for_article(article.article_id)) == 9

    current = Article.objects.get(pk=article.article_id)
    save_revision(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=current.row_version,
        snapshot=_snapshot(tag_ids=[item.tag_id for item in tags[1:11]]),
        capacity_check=lambda: None,
    )
    overflow = restore_tag(actor_id=admin.id, tag_id=tags[0].tag_id, **_context())
    conflict_model = apps.get_model("content", "TagRestoreConflict")
    assert overflow.restored_article_count == 0
    assert overflow.conflict_count == 1
    assert conflict_model.objects.filter(resolved_at__isnull=True).count() == 1
    assert len(tags_for_article(article.article_id)) == 10

    current = Article.objects.get(pk=article.article_id)
    save_revision(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=current.row_version,
        snapshot=_snapshot(tag_ids=[item.tag_id for item in tags[1:10]]),
        capacity_check=lambda: None,
    )
    restored = restore_tag(actor_id=admin.id, tag_id=tags[0].tag_id, **_context())
    assert restored.restored_article_count == 1
    assert restored.conflict_count == 0
    assert conflict_model.objects.filter(resolved_at__isnull=True).count() == 0
    assert len(tags_for_article(article.article_id)) == 10
    assert active_tag(tags[0].tag_id).state == Tag.State.ACTIVE

    outbox_model = apps.get_model("core", "OutboxEvent")
    assert (
        outbox_model.objects.filter(event_type="tag.restore_conflict.v1").count() == 1
    )
