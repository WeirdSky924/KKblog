import threading
from collections.abc import Callable
from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import IntegrityError, close_old_connections
from django.utils import timezone

from apps.accounts.models import Account, RoleAssignment
from apps.accounts.services.bootstrap import bootstrap_administrator
from apps.accounts.services.invites import (
    InviteError,
    generate_invite_codes,
    redeem_invite,
)
from apps.comments.models import Comment, DiscussionThread
from apps.comments.services.publication import (
    CommentPublicationOutcome,
    publish_due_comment,
)
from apps.content.models import Article, ArticleRevision, Tag
from apps.content.public import propose_tag
from apps.core.ids import new_ulid
from apps.exchange.models import ExportJob

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str, *, author: bool = False) -> Account:
    account = Account.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    if author:
        RoleAssignment.objects.create(
            account=account,
            role=RoleAssignment.Role.AUTHOR,
        )
    return account


def _run_two(worker: Callable[[int], str]) -> list[str]:
    barrier = threading.Barrier(2)
    results: list[str] = []
    failures: list[BaseException] = []

    def run(number: int) -> None:
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            results.append(worker(number))
        except BaseException as exc:
            failures.append(exc)
        finally:
            close_old_connections()

    threads = [threading.Thread(target=run, args=(number,)) for number in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert not [thread for thread in threads if thread.is_alive()]
    assert failures == []
    return results


def test_nickname_casefold_unique_index_is_the_concurrent_arbiter() -> None:
    def create(number: int) -> str:
        try:
            Account.objects.create_account(
                email=f"nickname-{number}@kaj.test",
                password="Valid-password-1",
                nickname=("Straße" if number == 0 else "STRASSE"),
            )
        except IntegrityError:
            return "conflict"
        return "created"

    assert sorted(_run_two(create)) == ["conflict", "created"]
    assert Account.objects.filter(normalized_nickname="strasse").count() == 1


def test_invite_row_lock_allows_only_one_concurrent_redemption() -> None:
    admin = bootstrap_administrator(
        email="admin@kaj.test",
        initial_password="One-time-password-1!",
        production=False,
    )
    issued = generate_invite_codes(
        count=1,
        validity_days=7,
        actor_id=admin.id,
        trace_code="KJ-QA001-INVITE",
        client_ip="127.0.0.1",
        audit_writer=lambda **values: values,
    )[0]
    accounts = [_account(f"invite-{number}") for number in range(2)]

    def redeem(number: int) -> str:
        try:
            redeem_invite(raw_code=issued.raw_code, account_id=accounts[number].id)
        except InviteError:
            return "rejected"
        return "redeemed"

    assert sorted(_run_two(redeem)) == ["redeemed", "rejected"]


def test_revision_sequence_unique_constraint_allows_one_writer() -> None:
    author = _account("revision-author")
    article = Article.objects.create(author=author)
    first = ArticleRevision.objects.create(
        article=article,
        sequence=1,
        created_by=author,
        content_format=ArticleRevision.ContentFormat.MARKDOWN,
        title="初始修订",
        body_markdown="正文",
    )
    article.working_revision = first
    article.save(update_fields=("working_revision", "updated_at"))

    def create(number: int) -> str:
        try:
            ArticleRevision.objects.create(
                article_id=article.id,
                sequence=2,
                based_on_id=first.id,
                created_by_id=author.id,
                content_format=ArticleRevision.ContentFormat.MARKDOWN,
                title=f"并发修订 {number}",
                body_markdown="正文",
            )
        except IntegrityError:
            return "conflict"
        return "created"

    assert sorted(_run_two(create)) == ["conflict", "created"]
    assert ArticleRevision.objects.filter(article=article, sequence=2).count() == 1


def test_tag_casefold_concurrency_returns_one_canonical_tag() -> None:
    authors = [_account(f"tag-author-{number}", author=True) for number in range(2)]

    def propose(number: int) -> str:
        result = propose_tag(
            actor_id=authors[number].id,
            name=("Straße" if number == 0 else "STRASSE"),
        )
        return str(result.tag_id)

    results = _run_two(propose)
    assert len(set(results)) == 1
    assert Tag.objects.filter(normalized_name="strasse").count() == 1


def test_comment_conditional_update_publishes_once_for_two_workers() -> None:
    owner = _account("comment-owner")
    thread = DiscussionThread.objects.create(
        target_type=DiscussionThread.TargetType.ARTICLE,
        target_id=new_ulid(),
        owner=owner,
    )
    comment_id = new_ulid()
    now = timezone.now()
    comment = Comment.objects.create(
        id=comment_id,
        thread=thread,
        parent=None,
        root_id=comment_id,
        author=owner,
        author_kind=Comment.AuthorKind.ACCOUNT,
        body="等待公开",
        state=Comment.State.BUFFERED,
        visible_at=now - timedelta(minutes=1),
        depth=0,
        reply_count=0,
        client_ip="192.0.2.40",
        created_at=now - timedelta(minutes=11),
    )

    def publish(_number: int) -> str:
        return publish_due_comment(comment_id=comment.id, now=now).outcome

    assert sorted(_run_two(publish)) == sorted(
        [
            CommentPublicationOutcome.PUBLISHED,
            CommentPublicationOutcome.ALREADY_VISIBLE,
        ]
    )
    comment.refresh_from_db()
    assert comment.state == Comment.State.VISIBLE


def test_export_partial_unique_constraint_allows_one_active_job() -> None:
    administrator = _account("export-admin")
    started_at = timezone.now()

    def create(_number: int) -> str:
        try:
            ExportJob.objects.create(
                requested_by_id=administrator.id,
                scope=ExportJob.Scope.ALL,
                scope_author_id=None,
                scope_section_id=None,
                requested_article_ids=[],
                started_at=started_at,
            )
        except IntegrityError:
            return "conflict"
        return "created"

    assert sorted(_run_two(create)) == ["conflict", "created"]
    assert (
        ExportJob.objects.filter(
            state__in=(ExportJob.State.RUNNING, ExportJob.State.CANCEL_REQUESTED)
        ).count()
        == 1
    )
