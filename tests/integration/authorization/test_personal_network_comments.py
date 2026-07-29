from datetime import timedelta

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import IpBlock, LoginSession
from apps.comments.models import Comment, DiscussionThread
from apps.content.public import Visibility
from apps.core.ids import new_ulid
from apps.moderation.models import Report
from apps.notifications.models import Notification, NotificationReceipt

from .conftest import IdentityMatrix
from .test_article_privacy import _published

pytestmark = pytest.mark.django_db(transaction=True)


def _broadcast(*, recipient, headline: str) -> Notification:
    notification = Notification.objects.create(
        template_key="admin.broadcast.v1",
        target_type="broadcast",
        target_id=new_ulid(),
        payload_safe={"headline": headline, "message": f"{headline}正文"},
    )
    NotificationReceipt.objects.create(
        notification=notification,
        recipient=recipient,
    )
    return notification


def test_notification_get_post_and_htmx_are_strictly_recipient_scoped(
    identities: IdentityMatrix,
) -> None:
    user_notice = _broadcast(recipient=identities.user, headline="仅普通用户可见")
    owner_notice = _broadcast(recipient=identities.owner, headline="仅作者可见")

    user_page = identities.clients["user"].get(reverse("notifications:list"))
    assert user_page.status_code == 200
    assert "仅普通用户可见" in user_page.content.decode()
    assert "仅作者可见" not in user_page.content.decode()

    owner_page = identities.clients["owner"].get(reverse("notifications:list"))
    assert "仅作者可见" in owner_page.content.decode()
    assert "仅普通用户可见" not in owner_page.content.decode()

    denied = identities.clients["user"].post(
        reverse("notifications:open", args=(owner_notice.id,)),
        HTTP_HX_REQUEST="true",
    )
    assert denied.status_code == 404
    assert (
        NotificationReceipt.objects.get(
            notification=owner_notice,
            recipient=identities.owner,
        ).read_at
        is None
    )

    opened = identities.clients["user"].post(
        reverse("notifications:open", args=(user_notice.id,)),
        HTTP_HX_REQUEST="true",
    )
    assert opened.status_code == 200
    assert (
        NotificationReceipt.objects.get(
            notification=user_notice,
            recipient=identities.user,
        ).read_at
        is not None
    )

    identities.clients["owner"].post(
        reverse("notifications:mark-all-read"),
        HTTP_HX_REQUEST="true",
    )
    assert (
        NotificationReceipt.objects.get(
            notification=owner_notice,
            recipient=identities.owner,
        ).read_at
        is not None
    )


def test_blocked_ip_forces_valid_session_to_guest_and_rejects_all_writes(
    identities: IdentityMatrix,
) -> None:
    blocked_address = "203.0.113.70"
    token, session = LoginSession.issue(
        account=identities.user,
        remember=False,
        client_ip=blocked_address,
    )
    IpBlock.objects.create(
        address=blocked_address,
        note="绝不能向用户泄露的备注",
        created_by=identities.admin,
    )
    client = identities.clients["visitor"]
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token

    public = client.get(reverse("public:home"), REMOTE_ADDR=blocked_address)
    assert public.status_code == 200
    assert "你已登录" not in public.content.decode()

    for method, url, payload in (
        ("get", reverse("accounts:settings"), None),
        ("get", reverse("notifications:list"), None),
        ("post", reverse("notifications:mark-all-read"), {}),
        ("post", reverse("accounts:login"), {"action": "password"}),
    ):
        response = getattr(client, method)(
            url,
            payload or {},
            REMOTE_ADDR=blocked_address,
        )
        assert response.status_code == 403, (method, url)
        body = response.content.decode()
        assert "当前网络暂时受限" in body
        assert "绝不能向用户泄露的备注" not in body

    session.refresh_from_db()
    assert session.revoked_at is None


def _visible_comment(identities: IdentityMatrix):
    article = _published(
        identities,
        visibility=Visibility.PUBLIC,
        title="评论权限文章",
    )
    thread = DiscussionThread.objects.create(
        target_type=DiscussionThread.TargetType.ARTICLE,
        target_id=article.article_id,
        owner=identities.owner,
    )
    comment_id = new_ulid()
    now = timezone.now()
    comment = Comment.objects.create(
        id=comment_id,
        thread=thread,
        parent=None,
        root_id=comment_id,
        author=identities.user,
        author_kind=Comment.AuthorKind.ACCOUNT,
        body="权限矩阵评论",
        state=Comment.State.VISIBLE,
        visible_at=now,
        depth=0,
        reply_count=0,
        client_ip="198.51.100.11",
        created_at=now - timedelta(minutes=10),
    )
    return article, comment


def test_comment_reply_delete_and_report_capability_matrix(
    identities: IdentityMatrix,
) -> None:
    article, comment = _visible_comment(identities)
    reply_url = reverse("comments:comment-reply-confirm", args=(comment.id,))
    report_url = reverse("moderation:report-confirm", args=(comment.id,))
    delete_url = reverse(
        "article:comment-delete-confirm", args=(article.article_id, comment.id)
    )

    assert identities.clients["visitor"].get(reply_url).status_code == 404
    assert identities.clients["visitor"].get(report_url).status_code == 403
    for identity in ("user", "owner", "other_author", "admin"):
        assert identities.clients[identity].get(reply_url).status_code == 200, identity
        assert identities.clients[identity].get(report_url).status_code == 200, identity

    assert (
        identities.clients["user"].get(delete_url, {"mode": "self"}).status_code == 200
    )
    assert (
        identities.clients["owner"].get(delete_url, {"mode": "owner"}).status_code
        == 200
    )
    assert (
        identities.clients["admin"].get(delete_url, {"mode": "admin"}).status_code
        == 200
    )
    assert (
        identities.clients["other_author"].get(delete_url, {"mode": "self"}).status_code
        == 404
    )
    comment.refresh_from_db()
    assert comment.state == Comment.State.VISIBLE

    create_url = reverse("moderation:report-create", args=(comment.id,))
    denied = identities.clients["visitor"].post(
        create_url,
        {"reason": "SPAM", "description": "伪造举报"},
        HTTP_HX_REQUEST="true",
    )
    assert denied.status_code == 403
    assert Report.objects.count() == 0

    created = identities.clients["other_author"].post(
        create_url,
        {"reason": "SPAM", "description": "重复广告"},
        HTTP_HX_REQUEST="true",
    )
    assert created.status_code == 201
    report = Report.objects.get()
    assert report.reporter_id == identities.other_author.id
    assert report.target_comment_id == comment.id
