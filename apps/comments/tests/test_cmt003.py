from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
from uuid import uuid4

import pytest
from django.apps import apps
from django.db import close_old_connections, transaction

from apps.comments.cooldown import CooldownReservation
from apps.comments.models import Comment, DiscussionThread
from apps.comments.ports import CommentAuthorIdentity
from apps.comments.presentation.authors import comment_author_presentation
from apps.comments.services.posting import CommentPostingError
from apps.comments.services.replies import reply_to_comment
from apps.comments.services.threads import sync_article_thread
from apps.content.public import (
    ArticleSnapshot,
    ContentFormat,
    create_article,
    create_section,
    prepare_publication,
    publish_article,
)
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str, *, roles: tuple[str, ...] = ()):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    for role in roles:
        role_model.objects.create(account=account, role=role)
    return account


def _published_article(author, *, comments_enabled: bool = True) -> str:
    section = create_section(
        actor_id=author.id,
        name=f"回复分区-{uuid4()}",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    draft = create_article(
        actor_id=author.id,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.MARKDOWN,
            title="回复测试文章",
            body="正文",
            section_id=section.section_id,
            comments_enabled=comments_enabled,
        ),
        capacity_check=lambda: None,
    )
    published_at = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    review = prepare_publication(
        actor_id=author.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        clock=FrozenClock(published_at),
    )
    publish_article(
        actor_id=author.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
        clock=FrozenClock(published_at),
    )
    return draft.article_id


@dataclass
class _Policy:
    active_ids: set = field(default_factory=set)
    blocked_ips: set[str] = field(default_factory=set)
    administrator_ids: set = field(default_factory=set)
    identities: dict = field(default_factory=dict)

    def is_active_account(self, account_id) -> bool:
        return account_id in self.active_ids

    def is_administrator(self, account_id) -> bool:
        return account_id in self.administrator_ids

    def is_ip_blocked(self, client_ip: str) -> bool:
        return client_ip in self.blocked_ips

    def public_identity(self, account_id):
        return self.identities.get(account_id)


class _Cooldown:
    def __init__(self) -> None:
        self.ttls: list[int] = []
        self.rollbacks: list[CooldownReservation] = []
        self._lock = Lock()

    def reserve(self, *, subject_kind, subject_value, ttl_seconds):
        with self._lock:
            self.ttls.append(ttl_seconds)
        return CooldownReservation(
            key=f"reply:{subject_kind}:{subject_value}", token=str(uuid4())
        )

    def rollback(self, reservation):
        self.rollbacks.append(reservation)
        return True


def _top_level(
    thread: DiscussionThread,
    author,
    *,
    state: str = Comment.State.VISIBLE,
    body: str = "根评论",
) -> Comment:
    comment_id = new_ulid()
    return Comment.objects.create(
        id=comment_id,
        thread=thread,
        parent=None,
        root_id=comment_id,
        author=author,
        author_kind=Comment.AuthorKind.ACCOUNT,
        body=body,
        state=state,
        visible_at=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
        depth=0,
        reply_count=0,
        client_ip="192.0.2.1",
        created_at=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
    )


def _reply(
    *,
    parent_id: str,
    actor,
    policy: _Policy,
    cooldown: _Cooldown | None = None,
    now: datetime | None = None,
    client_ip: str = "192.0.2.20",
    image_refs: tuple[str, ...] = (),
):
    return reply_to_comment(
        parent_id=parent_id,
        actor_id=None if actor is None else actor.id,
        client_ip=client_ip,
        body="登录回复",
        image_refs=image_refs,
        trace_code=new_trace_code(),
        clock=FrozenClock(now or datetime(2026, 7, 24, 9, 0, tzinfo=UTC)),
        account_policy=policy,
        cooldown_store=cooldown or _Cooldown(),
    )


def test_reply_requires_active_login_allowed_parent_and_no_images() -> None:
    owner = _account("cmt003-owner", roles=("AUTHOR", "ADMINISTRATOR"))
    parent_author = _account("cmt003-parent")
    member = _account("cmt003-member")
    article_id = _published_article(owner)
    thread, _ = sync_article_thread(actor_id=owner.id, article_id=article_id)
    parent = _top_level(thread, parent_author, state=Comment.State.BUFFERED)
    policy = _Policy({owner.id, parent_author.id, member.id})
    cooldown = _Cooldown()

    with pytest.raises(CommentPostingError) as guest:
        _reply(parent_id=parent.id, actor=None, policy=policy, cooldown=cooldown)
    assert guest.value.code == "comments.login_required.v1"

    with pytest.raises(CommentPostingError) as hidden:
        _reply(parent_id=parent.id, actor=member, policy=policy, cooldown=cooldown)
    assert hidden.value.code == "comments.reply_unavailable.v1"

    with pytest.raises(CommentPostingError) as images:
        _reply(
            parent_id=parent.id,
            actor=parent_author,
            policy=policy,
            cooldown=cooldown,
            image_refs=("forged",),
        )
    assert images.value.code == "comments.reply_images_forbidden.v1"

    parent.state = Comment.State.DELETED
    parent.body = ""
    parent.deleted_by_kind = Comment.DeletedByKind.OWNER
    parent.save(update_fields=("state", "body", "deleted_by_kind", "updated_at"))
    with pytest.raises(CommentPostingError) as deleted:
        _reply(parent_id=parent.id, actor=owner, policy=policy, cooldown=cooldown)
    assert deleted.value.code == "comments.reply_unavailable.v1"
    assert cooldown.ttls == []


def test_reply_rechecks_network_account_and_comment_closure() -> None:
    owner = _account("cmt003-policy-owner", roles=("AUTHOR", "ADMINISTRATOR"))
    member = _account("cmt003-policy-member")
    article_id = _published_article(owner, comments_enabled=False)
    thread, _ = sync_article_thread(actor_id=owner.id, article_id=article_id)
    parent = _top_level(thread, owner)
    policy = _Policy({owner.id, member.id}, {"198.51.100.9"})

    with pytest.raises(CommentPostingError) as blocked:
        _reply(
            parent_id=parent.id,
            actor=member,
            policy=policy,
            client_ip="198.51.100.9",
        )
    assert blocked.value.code == "comments.network_restricted.v1"

    policy.active_ids.remove(member.id)
    with pytest.raises(CommentPostingError) as inactive:
        _reply(parent_id=parent.id, actor=member, policy=policy)
    assert inactive.value.code == "comments.account_unavailable.v1"

    policy.active_ids.add(member.id)
    with pytest.raises(CommentPostingError) as closed:
        _reply(parent_id=parent.id, actor=member, policy=policy)
    assert closed.value.code == "comments.closed.v1"


def test_reply_sets_root_depth_buffer_count_and_safe_created_event() -> None:
    owner = _account("cmt003-tree-owner", roles=("AUTHOR", "ADMINISTRATOR"))
    first_actor = _account("cmt003-tree-first")
    article_id = _published_article(owner)
    thread, _ = sync_article_thread(actor_id=owner.id, article_id=article_id)
    root = _top_level(thread, owner)
    policy = _Policy({owner.id, first_actor.id})
    now = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    cooldown = _Cooldown()

    first = _reply(
        parent_id=root.id,
        actor=first_actor,
        policy=policy,
        cooldown=cooldown,
        now=now,
    )
    second = _reply(
        parent_id=first.comment_id,
        actor=owner,
        policy=policy,
        cooldown=cooldown,
        now=now + timedelta(seconds=1),
    )

    first_row = Comment.objects.get(pk=first.comment_id)
    second_row = Comment.objects.get(pk=second.comment_id)
    root.refresh_from_db()
    assert (first_row.parent_id, first_row.root_id, first_row.depth) == (
        root.id,
        root.id,
        1,
    )
    assert (second_row.parent_id, second_row.root_id, second_row.depth) == (
        first_row.id,
        root.id,
        2,
    )
    assert first_row.state == second_row.state == Comment.State.BUFFERED
    assert first_row.visible_at == now + timedelta(minutes=10)
    assert second_row.visible_at == now + timedelta(minutes=10, seconds=1)
    assert root.reply_count == 2
    assert cooldown.ttls == [60, 60]

    event_model = apps.get_model("core", "OutboxEvent")
    events = event_model.objects.filter(
        event_type="comment.created.v1",
        aggregate_id__in=(first_row.id, second_row.id),
    )
    assert events.count() == 2
    assert all(event.payload["image_count"] == 0 for event in events)
    assert all("body" not in event.payload for event in events)
    assert all("ip" not in str(event.payload).casefold() for event in events)


def test_concurrent_replies_atomically_increment_root_count() -> None:
    owner = _account("cmt003-concurrent-owner", roles=("AUTHOR", "ADMINISTRATOR"))
    actors = [_account(f"cmt003-concurrent-{index}") for index in range(8)]
    article_id = _published_article(owner)
    thread, _ = sync_article_thread(actor_id=owner.id, article_id=article_id)
    root = _top_level(thread, owner)
    policy = _Policy({owner.id, *(actor.id for actor in actors)})
    cooldown = _Cooldown()

    def worker(actor) -> str:
        close_old_connections()
        try:
            return _reply(
                parent_id=root.id,
                actor=actor,
                policy=policy,
                cooldown=cooldown,
                client_ip="203.0.113.20",
            ).comment_id
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=8) as pool:
        reply_ids = list(pool.map(worker, actors))

    root.refresh_from_db()
    assert len(set(reply_ids)) == 8
    assert root.reply_count == 8
    assert Comment.objects.filter(root=root, parent=root).count() == 8


def test_depth_over_one_hundred_emits_one_thread_alert() -> None:
    owner = _account("cmt003-deep-owner", roles=("AUTHOR", "ADMINISTRATOR"))
    first_actor = _account("cmt003-deep-first")
    article_id = _published_article(owner)
    thread, _ = sync_article_thread(actor_id=owner.id, article_id=article_id)
    root = _top_level(thread, owner)
    policy = _Policy({owner.id, first_actor.id})
    parent = root
    with transaction.atomic():
        for depth in range(1, 101):
            parent = Comment.objects.create(
                id=new_ulid(),
                thread=thread,
                parent=parent,
                root=root,
                author=owner,
                author_kind=Comment.AuthorKind.ACCOUNT,
                body=f"深度 {depth}",
                state=Comment.State.VISIBLE,
                visible_at=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
                depth=depth,
                reply_count=0,
                client_ip="192.0.2.30",
                created_at=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
            )
        root.reply_count = 100
        root.save(update_fields=("reply_count", "updated_at"))

    depth_101 = _reply(
        parent_id=parent.id,
        actor=first_actor,
        policy=policy,
    )
    depth_102 = _reply(
        parent_id=depth_101.comment_id,
        actor=owner,
        policy=policy,
    )
    thread.refresh_from_db()
    root.refresh_from_db()
    event_model = apps.get_model("core", "OutboxEvent")
    alerts = event_model.objects.filter(event_type="comment.deep_thread.v1")

    assert depth_101.depth == 101
    assert depth_102.depth == 102
    assert root.reply_count == 102
    assert thread.deep_thread_alerted_at is not None
    assert alerts.count() == 1
    alert = alerts.get()
    assert alert.aggregate_id == str(thread.id)
    assert alert.payload["owner_id"] == str(owner.id)
    assert alert.payload["root_id"] == root.id
    assert alert.payload["depth"] == 101
    assert "body" not in alert.payload
    assert "ip" not in str(alert.payload).casefold()


def test_comment_author_presentation_links_only_active_accounts() -> None:
    account_id = uuid4()
    policy = _Policy(
        active_ids={account_id},
        identities={
            account_id: CommentAuthorIdentity(
                account_id=account_id,
                display_name="注册用户",
                profile_url=f"/people/{account_id}/",
            )
        },
    )

    account = comment_author_presentation(
        author_kind=Comment.AuthorKind.ACCOUNT,
        author_id=account_id,
        account_policy=policy,
    )
    anonymous = comment_author_presentation(
        author_kind=Comment.AuthorKind.ANONYMOUS,
        author_id=None,
        account_policy=policy,
    )
    deleted = comment_author_presentation(
        author_kind=Comment.AuthorKind.DELETED_ACCOUNT,
        author_id=None,
        account_policy=policy,
    )

    assert (account.label, account.profile_url) == (
        "注册用户",
        f"/people/{account_id}/",
    )
    assert (anonymous.label, anonymous.profile_url) == ("访客", None)
    assert (deleted.label, deleted.profile_url) == ("该账号已注销", None)


def test_reply_event_failure_rolls_back_tree_count_and_cooldown(monkeypatch) -> None:
    owner = _account("cmt003-rollback-owner", roles=("AUTHOR", "ADMINISTRATOR"))
    member = _account("cmt003-rollback-member")
    article_id = _published_article(owner)
    thread, _ = sync_article_thread(actor_id=owner.id, article_id=article_id)
    root = _top_level(thread, owner)
    policy = _Policy({owner.id, member.id})
    cooldown = _Cooldown()
    before_count = Comment.objects.count()

    def fail_event(*args, **kwargs):
        raise RuntimeError("synthetic outbox failure")

    monkeypatch.setattr(
        "apps.comments.services.replies.enqueue_event",
        fail_event,
    )
    with pytest.raises(RuntimeError, match="synthetic outbox failure"):
        _reply(
            parent_id=root.id,
            actor=member,
            policy=policy,
            cooldown=cooldown,
        )

    root.refresh_from_db()
    assert Comment.objects.count() == before_count
    assert root.reply_count == 0
    assert len(cooldown.rollbacks) == 1
