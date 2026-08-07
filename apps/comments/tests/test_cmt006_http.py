from datetime import timedelta
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.comments.models import Comment
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


def _published_article(owner, administrator) -> str:
    section = create_section(
        actor_id=administrator.id,
        name=f"删除分区-{uuid4()}",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    draft = create_article(
        actor_id=owner.id,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.MARKDOWN,
            title="评论删除验收文章",
            body="正文",
            section_id=section.section_id,
        ),
        capacity_check=lambda: None,
    )
    now = timezone.now() - timedelta(days=1)
    review = prepare_publication(
        actor_id=owner.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        clock=FrozenClock(now),
    )
    publish_article(
        actor_id=owner.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
        clock=FrozenClock(now),
    )
    return draft.article_id


def _comment(thread, author, *, parent=None, root=None, depth=0, body="可删除评论"):
    comment_id = new_ulid()
    now = timezone.now() - timedelta(minutes=20)
    created_at = now + timedelta(seconds=depth)
    return Comment.objects.create(
        id=comment_id,
        thread=thread,
        parent=parent,
        root_id=comment_id if root is None else root.id,
        author=author,
        author_kind=Comment.AuthorKind.ACCOUNT,
        body=body,
        state=Comment.State.VISIBLE,
        visible_at=created_at,
        depth=depth,
        reply_count=1 if root is None else 0,
        client_ip="192.0.2.90",
        created_at=created_at,
    )


def _client(account, address: str) -> Client:
    token, _ = apps.get_model("accounts", "LoginSession").issue(
        account=account,
        remember=False,
    )
    client = Client(REMOTE_ADDR=address)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token
    return client


def test_delete_capabilities_and_self_delete_htmx_flow() -> None:
    administrator = _account("cmt006-http-admin", roles=("ADMINISTRATOR",))
    owner = _account("cmt006-http-owner", roles=("AUTHOR",))
    member = _account("cmt006-http-member")
    article_id = _published_article(owner, administrator)
    thread, _ = sync_article_thread(actor_id=owner.id, article_id=article_id)
    root = _comment(thread, member, body="成员准备删除的评论")
    child = _comment(
        thread, owner, parent=root, root=root, depth=1, body="保留的子回复"
    )
    detail_url = reverse("article:detail", kwargs={"article_id": article_id})
    confirm_url = reverse(
        "article:comment-delete-confirm",
        kwargs={"article_id": article_id, "comment_id": root.id},
    )
    delete_url = reverse(
        "article:comment-delete",
        kwargs={"article_id": article_id, "comment_id": root.id},
    )

    guest_html = Client(REMOTE_ADDR="198.51.100.90").get(detail_url).content.decode()
    assert "data-comment-delete-mode" not in guest_html

    member_client = _client(member, "198.51.100.91")
    member_html = member_client.get(detail_url).content.decode()
    assert 'data-comment-delete-mode="self"' in member_html
    assert 'data-comment-delete-mode="owner"' not in member_html
    assert 'data-comment-delete-mode="admin"' not in member_html

    owner_html = _client(owner, "198.51.100.92").get(detail_url).content.decode()
    assert 'data-comment-delete-mode="owner"' in owner_html
    admin_html = (
        _client(administrator, "198.51.100.93").get(detail_url).content.decode()
    )
    assert 'data-comment-delete-mode="admin"' in admin_html

    confirm = member_client.get(
        confirm_url,
        {"mode": "self"},
        HTTP_HX_REQUEST="true",
    )
    assert confirm.status_code == 200
    confirm_html = confirm.content.decode()
    assert "data-confirm-dialog" in confirm_html
    assert f'hx-post="{delete_url}"' in confirm_html
    assert "现有回复不会消失" in confirm_html
    assert 'name="reason"' not in confirm_html
    assert "autofocus" not in confirm_html

    deleted = member_client.post(
        delete_url,
        {"mode": "self", "reason": "伪造原因"},
        HTTP_HX_REQUEST="true",
    )
    assert deleted.status_code == 200
    deleted_html = deleted.content.decode()
    assert "该评论已删除" in deleted_html
    assert "成员准备删除的评论" not in deleted_html
    assert "保留的子回复" in deleted_html
    assert 'data-comment-delete-mode="self"' not in deleted_html
    root.refresh_from_db()
    child.refresh_from_db()
    assert root.deleted_by_kind == Comment.DeletedByKind.SELF
    assert root.deletion_reason is None
    assert child.parent_id == root.id
    assert child.state == Comment.State.VISIBLE


def test_admin_reason_is_final_and_forged_mode_is_rejected() -> None:
    administrator = _account("cmt006-final-admin", roles=("ADMINISTRATOR",))
    owner = _account("cmt006-final-owner", roles=("AUTHOR",))
    member = _account("cmt006-final-member")
    article_id = _published_article(owner, administrator)
    thread, _ = sync_article_thread(actor_id=owner.id, article_id=article_id)
    comment = _comment(thread, member, body="管理员删除目标")
    confirm_url = reverse(
        "article:comment-delete-confirm",
        kwargs={"article_id": article_id, "comment_id": comment.id},
    )
    delete_url = reverse(
        "article:comment-delete",
        kwargs={"article_id": article_id, "comment_id": comment.id},
    )
    admin_client = _client(administrator, "198.51.100.94")

    confirm = admin_client.get(
        confirm_url,
        {"mode": "admin"},
        HTTP_HX_REQUEST="true",
    )
    assert confirm.status_code == 200
    html = confirm.content.decode()
    assert "删除后不能申诉" in html
    assert 'name="reason"' in html
    assert 'maxlength="200"' in html

    forged = _client(member, "198.51.100.95").post(
        delete_url,
        {"mode": "admin", "reason": "越权"},
        HTTP_HX_REQUEST="true",
    )
    assert forged.status_code == 404
    comment.refresh_from_db()
    assert comment.state == Comment.State.VISIBLE

    invalid = admin_client.post(
        delete_url,
        {"mode": "admin", "reason": "<script>"},
        HTTP_HX_REQUEST="true",
    )
    assert invalid.status_code == 422
    assert "删除原因需为 200 个字符以内的纯文本" in invalid.content.decode()
    assert invalid.headers["HX-Retarget"] == "#comment-dialog-host"
    assert invalid.headers["HX-Reswap"] == "innerHTML"
    comment.refresh_from_db()
    assert comment.state == Comment.State.VISIBLE

    deleted = admin_client.post(
        delete_url,
        {"mode": "admin", "reason": "持续发布无关内容"},
        HTTP_HX_REQUEST="true",
    )
    assert deleted.status_code == 200
    comment.refresh_from_db()
    assert comment.deleted_by_kind == Comment.DeletedByKind.ADMIN
    assert comment.deletion_reason == "持续发布无关内容"
    event = apps.get_model("core", "OutboxEvent").objects.get(
        event_type="comment.deleted.v1",
        aggregate_id=comment.id,
    )
    assert set(event.payload["recipient_ids"]) == {str(member.id), str(owner.id)}
