from datetime import timedelta
from io import BytesIO
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from redis import Redis

from apps.comments.models import Comment
from apps.comments.services import sync_guestbook_thread, update_guestbook_settings
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code

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


def _client(account, address: str) -> Client:
    token, _ = apps.get_model("accounts", "LoginSession").issue(
        account=account,
        remember=False,
    )
    client = Client(REMOTE_ADDR=address)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token
    return client


def _visible_comment(thread, author, body: str) -> Comment:
    identity = new_ulid()
    now = timezone.now() - timedelta(minutes=20)
    return Comment.objects.create(
        id=identity,
        thread=thread,
        parent=None,
        root_id=identity,
        author=author,
        author_kind=Comment.AuthorKind.ACCOUNT,
        body=body,
        state=Comment.State.VISIBLE,
        visible_at=now,
        depth=0,
        reply_count=0,
        client_ip="192.0.2.117",
        created_at=now,
    )


def _png() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (12, 10), (122, 35, 68)).save(stream, format="PNG")
    return stream.getvalue()


def _clear_redis(namespace: str) -> None:
    client = Redis.from_url(settings.REDIS_URL, decode_responses=False)
    keys = tuple(client.scan_iter(match=f"{namespace}:*"))
    if keys:
        client.delete(*keys)


def test_public_guestbook_default_login_gate_close_and_sorting() -> None:
    namespace = f"kaj-http-cmt007-public-{uuid4()}"
    administrator = _account("cmt007-http-admin", roles=("AUTHOR", "ADMINISTRATOR"))
    url = reverse("public:guestbook")
    post_url = reverse("public:guestbook-comment-create")
    page_url = reverse("public:guestbook-comment-page")
    visitor = Client(REMOTE_ADDR="198.51.100.117")

    try:
        with override_settings(COMMENTS_COOLDOWN_NAMESPACE=namespace):
            page = visitor.get(url)
            assert page.status_code == 200
            html = page.content.decode()
            assert "<h1" in html and "留言板" in html
            assert f'action="{post_url}"' in html
            assert "留言内容" in html
            assert 'placeholder="写下留言"' in html
            thread = sync_guestbook_thread()
            assert thread.owner_id == administrator.id
            assert (
                apps.get_model("comments", "DiscussionThread")
                .objects.filter(target_type="GUESTBOOK", target_id="site")
                .count()
                == 1
            )

            invalid = visitor.post(
                post_url,
                {"body": "字" * 101},
                HTTP_HX_REQUEST="true",
            )
            assert invalid.status_code == 422
            assert "字" * 101 in invalid.content.decode()

            created = visitor.post(
                post_url,
                {"body": "访客留下的缓冲留言"},
                HTTP_HX_REQUEST="true",
            )
            assert created.status_code == 201
            assert "访客留下的缓冲留言" in created.content.decode()
            assert settings.COMMENTS_RECEIPT_COOKIE_NAME in created.cookies
            comment = Comment.objects.get(body="访客留下的缓冲留言")
            Comment.objects.filter(pk=comment.pk).update(
                state=Comment.State.VISIBLE,
                visible_at=comment.created_at,
            )
            later = _visible_comment(thread, administrator, "稍后发布的留言")
            later_at = timezone.now()
            Comment.objects.filter(pk=later.pk).update(
                created_at=later_at,
                visible_at=later_at,
            )
            latest = visitor.get(page_url, {"sort": "latest"})
            assert latest.status_code == 200
            latest_html = latest.content.decode()
            assert latest_html.index("稍后发布的留言") < latest_html.index(
                "访客留下的缓冲留言"
            )

            update_guestbook_settings(
                actor_id=administrator.id,
                comments_enabled=True,
                post_login_required=True,
                client_ip="198.51.100.118",
                trace_code=new_trace_code(),
            )
            gated = Client(REMOTE_ADDR="198.51.100.119").get(url)
            gated_html = gated.content.decode()
            assert "登录后才能发表留言" in gated_html
            assert f'action="{post_url}"' not in gated_html
            denied = Client(REMOTE_ADDR="198.51.100.120").post(
                post_url,
                {"body": "访客不能发布"},
                HTTP_HX_REQUEST="true",
            )
            assert denied.status_code == 403

            update_guestbook_settings(
                actor_id=administrator.id,
                comments_enabled=False,
                post_login_required=False,
                client_ip="198.51.100.121",
                trace_code=new_trace_code(),
            )
            closed = visitor.get(url)
            closed_html = closed.content.decode()
            assert "留言板已关闭，既有留言仍会保留" in closed_html
            assert "访客留下的缓冲留言" in closed_html
            assert f'action="{post_url}"' not in closed_html
            rejected = visitor.post(
                post_url,
                {"body": "关闭后不能发布"},
                HTTP_HX_REQUEST="true",
            )
            assert rejected.status_code == 409
    finally:
        _clear_redis(namespace)


def test_guestbook_reuses_image_reply_and_admin_owner_delete(tmp_path) -> None:
    namespace = f"kaj-http-cmt007-actions-{uuid4()}"
    administrator = _account("cmt007-actions-admin", roles=("AUTHOR", "ADMINISTRATOR"))
    member = _account("cmt007-actions-member")
    thread = sync_guestbook_thread()
    root = _visible_comment(thread, member, "等待回复与管理的留言")
    page_url = reverse("public:guestbook")
    post_url = reverse("public:guestbook-comment-create")
    upload_url = reverse("public:guestbook-comment-image")
    reply_confirm_url = reverse(
        "comments:comment-reply-confirm", kwargs={"comment_id": root.id}
    )
    reply_url = reverse("comments:comment-reply", kwargs={"comment_id": root.id})
    delete_confirm_url = reverse(
        "comments:comment-delete-confirm", kwargs={"comment_id": root.id}
    )
    delete_url = reverse("comments:comment-delete", kwargs={"comment_id": root.id})
    member_client = _client(member, "198.51.100.122")
    admin_client = _client(administrator, "198.51.100.123")

    try:
        with override_settings(
            COMMENTS_COOLDOWN_NAMESPACE=namespace,
            MEDIA_ROOT=tmp_path,
        ):
            page = member_client.get(page_url)
            html = page.content.decode()
            assert f'hx-get="{reply_confirm_url}"' in html
            assert f'data-media-upload-url="{upload_url}"' in html

            upload = member_client.post(
                upload_url,
                {
                    "file": SimpleUploadedFile(
                        "guestbook.png", _png(), content_type="image/png"
                    )
                },
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            assert upload.status_code == 201
            image_ref = upload.context["upload"].image_ref
            posted = member_client.post(
                post_url,
                {"body": "带图片的留言", "image_ref_1": image_ref},
                HTTP_HX_REQUEST="true",
            )
            assert posted.status_code == 201
            image_comment = Comment.objects.get(body="带图片的留言")
            binding = apps.get_model("media", "MediaBinding").objects.get(
                target_type="comment", target_id=image_comment.id
            )
            assert binding.asset.owner_id == member.id
            assert "/guestbook/comments/" in binding.asset.storage_key
            _clear_redis(namespace)

            dialog = member_client.get(reply_confirm_url, HTTP_HX_REQUEST="true")
            assert dialog.status_code == 200
            dialog_html = dialog.content.decode()
            assert f'hx-post="{reply_url}"' in dialog_html
            assert "回复内容" in dialog_html
            assert "data-media-picker" not in dialog_html
            invalid = member_client.post(
                reply_url,
                {"body": ""},
                HTTP_HX_REQUEST="true",
            )
            assert invalid.status_code == 422
            replied = member_client.post(
                reply_url,
                {"body": "登录用户的真实回复"},
                HTTP_HX_REQUEST="true",
            )
            assert replied.status_code == 201
            reply = Comment.objects.get(body="登录用户的真实回复")
            assert (reply.parent_id, reply.root_id, reply.thread_id) == (
                root.id,
                root.id,
                thread.id,
            )

            confirm = admin_client.get(
                delete_confirm_url,
                {"mode": "owner"},
                HTTP_HX_REQUEST="true",
            )
            assert confirm.status_code == 200
            assert "删除这条留言" in confirm.content.decode()
            deleted = admin_client.post(
                delete_url,
                {"mode": "owner"},
                HTTP_HX_REQUEST="true",
            )
            assert deleted.status_code == 200
            deleted_html = deleted.content.decode()
            assert "该留言已删除" in deleted_html
            assert "登录用户的真实回复" in deleted_html
            assert "回复等待公开" in deleted_html
            root.refresh_from_db()
            reply.refresh_from_db()
            assert root.deleted_by_kind == Comment.DeletedByKind.OWNER
            assert reply.state == Comment.State.BUFFERED
    finally:
        _clear_redis(namespace)
