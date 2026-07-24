from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.apps import apps

from apps.comments.cooldown import CommentCooldownActive, CooldownReservation
from apps.comments.models import Comment, DiscussionThread
from apps.comments.ports import CommentMediaError
from apps.comments.services.posting import CommentPostingError, create_top_level_comment
from apps.content.public import (
    ArticleSnapshot,
    ContentFormat,
    create_article,
    create_section,
    prepare_publication,
    publish_article,
)
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


def _published_article(
    author,
    *,
    comments_enabled: bool = True,
    post_login_required: bool = False,
) -> str:
    section = create_section(
        actor_id=author.id,
        name=f"评论分区-{uuid4()}",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    draft = create_article(
        actor_id=author.id,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.MARKDOWN,
            title="评论测试文章",
            body="正文",
            section_id=section.section_id,
            comments_enabled=comments_enabled,
            comments_post_login=post_login_required,
        ),
        capacity_check=lambda: None,
    )
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    review = prepare_publication(
        actor_id=author.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        clock=FrozenClock(now),
    )
    publish_article(
        actor_id=author.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
        clock=FrozenClock(now),
    )
    return draft.article_id


@dataclass
class _AccountPolicy:
    active_ids: set
    blocked_ips: set[str]
    administrator_ids: set

    def is_active_account(self, account_id) -> bool:
        return account_id in self.active_ids

    def is_administrator(self, account_id) -> bool:
        return account_id in self.administrator_ids

    def is_ip_blocked(self, client_ip: str) -> bool:
        return client_ip in self.blocked_ips


class _Cooldown:
    def __init__(self) -> None:
        self.active: dict[tuple[str, str], CooldownReservation] = {}
        self.ttls: list[int] = []
        self.rolled_back: list[CooldownReservation] = []

    def reserve(
        self, *, subject_kind: str, subject_value: str, ttl_seconds: int
    ) -> CooldownReservation:
        key = (subject_kind, subject_value)
        if key in self.active:
            raise CommentCooldownActive(ttl_seconds)
        reservation = CooldownReservation(
            key=f"cooldown:{subject_kind}:{subject_value}", token=str(uuid4())
        )
        self.active[key] = reservation
        self.ttls.append(ttl_seconds)
        return reservation

    def rollback(self, reservation: CooldownReservation) -> None:
        self.rolled_back.append(reservation)
        for key, current in tuple(self.active.items()):
            if current == reservation:
                del self.active[key]


class _Media:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def bind_images(self, **kwargs) -> tuple[str, ...]:
        self.calls.append(kwargs)
        if self.fail:
            raise CommentMediaError(
                "media.binding_invalid.v1", "图片无法绑定，请重新选择。"
            )
        return tuple(
            f"asset-{index}" for index, _ in enumerate(kwargs["image_refs"], 1)
        )


def _post(
    *,
    article_id: str,
    actor_id,
    client_ip: str,
    body: str,
    clock: FrozenClock,
    account_policy: _AccountPolicy,
    cooldown: _Cooldown,
    media: _Media,
    image_refs: tuple[str, ...] = (),
):
    return create_top_level_comment(
        target_type="ARTICLE",
        target_id=article_id,
        actor_id=actor_id,
        client_ip=client_ip,
        body=body,
        image_refs=image_refs,
        trace_code=new_trace_code(),
        clock=clock,
        account_policy=account_policy,
        cooldown_store=cooldown,
        media_gateway=media,
    )


def test_guest_and_account_comments_use_distinct_cooldowns_and_ten_minute_buffer() -> (
    None
):
    author = _account("cmt002-author", roles=("AUTHOR", "ADMINISTRATOR"))
    member = _account("cmt002-member")
    article_id = _published_article(author)
    policy = _AccountPolicy({author.id, member.id}, set(), set())
    cooldown = _Cooldown()
    media = _Media()
    now = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)

    guest = _post(
        article_id=article_id,
        actor_id=None,
        client_ip="198.51.100.10",
        body="访客评论",
        clock=FrozenClock(now),
        account_policy=policy,
        cooldown=cooldown,
        media=media,
    )
    member_result = _post(
        article_id=article_id,
        actor_id=member.id,
        client_ip="198.51.100.11",
        body="登录评论",
        clock=FrozenClock(now),
        account_policy=policy,
        cooldown=cooldown,
        media=media,
    )
    administrator_author = _post(
        article_id=article_id,
        actor_id=author.id,
        client_ip="198.51.100.12",
        body="管理员兼作者也按登录用户规则评论",
        clock=FrozenClock(now),
        account_policy=policy,
        cooldown=cooldown,
        media=media,
    )

    assert cooldown.ttls == [300, 60, 60]
    assert guest.visible_at == now + timedelta(minutes=10)
    assert member_result.visible_at == now + timedelta(minutes=10)
    assert administrator_author.visible_at == now + timedelta(minutes=10)
    assert Comment.objects.get(pk=guest.comment_id).author_kind == "ANONYMOUS"
    assert Comment.objects.get(pk=member_result.comment_id).author_id == member.id
    assert DiscussionThread.objects.get(target_id=article_id).owner_id == author.id

    event_model = apps.get_model("core", "OutboxEvent")
    events = event_model.objects.filter(event_type="comment.created.v1").order_by(
        "occurred_at", "event_id"
    )
    assert events.count() == 3
    assert all("body" not in event.payload for event in events)
    assert all("ip" not in str(event.payload).casefold() for event in events)


def test_posting_enforces_thread_permissions_account_state_and_ip_block() -> None:
    author = _account("cmt002-policy-author", roles=("AUTHOR", "ADMINISTRATOR"))
    member = _account("cmt002-policy-member")
    policy = _AccountPolicy({author.id, member.id}, {"203.0.113.9"}, set())
    now = FrozenClock(datetime(2026, 7, 24, 10, 0, tzinfo=UTC))

    login_article = _published_article(author, post_login_required=True)
    with pytest.raises(CommentPostingError) as guest_denied:
        _post(
            article_id=login_article,
            actor_id=None,
            client_ip="203.0.113.1",
            body="需要登录",
            clock=now,
            account_policy=policy,
            cooldown=_Cooldown(),
            media=_Media(),
        )
    assert guest_denied.value.code == "comments.login_required.v1"

    closed_article = _published_article(author, comments_enabled=False)
    with pytest.raises(CommentPostingError) as closed:
        _post(
            article_id=closed_article,
            actor_id=member.id,
            client_ip="203.0.113.2",
            body="评论关闭",
            clock=now,
            account_policy=policy,
            cooldown=_Cooldown(),
            media=_Media(),
        )
    assert closed.value.code == "comments.closed.v1"

    with pytest.raises(CommentPostingError) as blocked:
        _post(
            article_id=login_article,
            actor_id=member.id,
            client_ip="203.0.113.9",
            body="封禁网络",
            clock=now,
            account_policy=policy,
            cooldown=_Cooldown(),
            media=_Media(),
        )
    assert blocked.value.code == "comments.network_restricted.v1"

    policy.active_ids.remove(member.id)
    with pytest.raises(CommentPostingError) as inactive:
        _post(
            article_id=login_article,
            actor_id=member.id,
            client_ip="203.0.113.3",
            body="失效账户",
            clock=now,
            account_policy=policy,
            cooldown=_Cooldown(),
            media=_Media(),
        )
    assert inactive.value.code == "comments.account_unavailable.v1"


def test_body_image_and_duplicate_submission_boundaries() -> None:
    author = _account("cmt002-boundary-author", roles=("AUTHOR", "ADMINISTRATOR"))
    article_id = _published_article(author)
    policy = _AccountPolicy({author.id}, set(), set())
    cooldown = _Cooldown()
    media = _Media()
    now = FrozenClock(datetime(2026, 7, 24, 11, 0, tzinfo=UTC))

    accepted = _post(
        article_id=article_id,
        actor_id=None,
        client_ip="192.0.2.10",
        body="字" * 100,
        image_refs=("ref-1", "ref-2", "ref-3"),
        clock=now,
        account_policy=policy,
        cooldown=cooldown,
        media=media,
    )
    assert accepted.image_count == 3
    assert len(media.calls) == 1

    for body, refs, expected in (
        ("", (), "comments.body_invalid.v1"),
        ("字" * 101, (), "comments.body_invalid.v1"),
        ("有效", ("1", "2", "3", "4"), "comments.images_invalid.v1"),
        ("有效", ("same", "same"), "comments.images_invalid.v1"),
    ):
        with pytest.raises(CommentPostingError) as invalid:
            _post(
                article_id=article_id,
                actor_id=None,
                client_ip=f"192.0.2.{20 + len(refs) + len(body)}",
                body=body,
                image_refs=refs,
                clock=now,
                account_policy=policy,
                cooldown=_Cooldown(),
                media=_Media(),
            )
        assert invalid.value.code == expected

    with pytest.raises(CommentPostingError) as duplicate:
        _post(
            article_id=article_id,
            actor_id=None,
            client_ip="192.0.2.10",
            body="重复提交",
            clock=now,
            account_policy=policy,
            cooldown=cooldown,
            media=media,
        )
    assert duplicate.value.code == "comments.cooldown_active.v1"


def test_media_failure_rolls_back_comment_event_and_owned_cooldown_reservation() -> (
    None
):
    author = _account("cmt002-rollback-author", roles=("AUTHOR", "ADMINISTRATOR"))
    article_id = _published_article(author)
    policy = _AccountPolicy({author.id}, set(), set())
    cooldown = _Cooldown()
    before_comments = Comment.objects.count()
    event_model = apps.get_model("core", "OutboxEvent")
    before_events = event_model.objects.filter(event_type="comment.created.v1").count()

    with pytest.raises(CommentPostingError) as failed:
        _post(
            article_id=article_id,
            actor_id=None,
            client_ip="198.51.100.88",
            body="图片绑定失败",
            image_refs=("bad-ref",),
            clock=FrozenClock(datetime(2026, 7, 24, 12, 0, tzinfo=UTC)),
            account_policy=policy,
            cooldown=cooldown,
            media=_Media(fail=True),
        )

    assert failed.value.code == "comments.images_invalid.v1"
    assert Comment.objects.count() == before_comments
    assert (
        event_model.objects.filter(event_type="comment.created.v1").count()
        == before_events
    )
    assert len(cooldown.rolled_back) == 1
