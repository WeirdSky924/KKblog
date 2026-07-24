from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from PIL import Image
from redis import Redis

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


def _published_article(author, *, post_login_required: bool = False) -> str:
    section = create_section(
        actor_id=author.id,
        name=f"HTTP 评论分区-{uuid4()}",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    draft = create_article(
        actor_id=author.id,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.MARKDOWN,
            title="评论 HTTP 测试文章",
            body="页面正文",
            section_id=section.section_id,
            comments_post_login=post_login_required,
        ),
        capacity_check=lambda: None,
    )
    now = datetime(2026, 7, 24, 14, 0, tzinfo=UTC)
    clock = FrozenClock(now)
    review = prepare_publication(
        actor_id=author.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        clock=clock,
    )
    publish_article(
        actor_id=author.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
        clock=clock,
    )
    return draft.article_id


def _png() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (10, 10), (40, 120, 190)).save(stream, format="PNG")
    return stream.getvalue()


def _clear_redis(namespace: str) -> None:
    client = Redis.from_url(settings.REDIS_URL, decode_responses=False)
    keys = tuple(client.scan_iter(match=f"{namespace}:*"))
    if keys:
        client.delete(*keys)


def test_article_comment_htmx_keeps_anonymous_buffer_private_and_returns_422_429(
    tmp_path,
) -> None:
    namespace = f"kaj-http-cmt002-{uuid4()}"
    author = _account("cmt002-http-author", roles=("AUTHOR", "ADMINISTRATOR"))
    article_id = _published_article(author)
    detail_url = reverse("article:detail", kwargs={"article_id": article_id})
    post_url = reverse("article:comment-create", kwargs={"article_id": article_id})
    visitor = Client(REMOTE_ADDR="198.51.100.14")

    try:
        with override_settings(
            MEDIA_ROOT=tmp_path,
            COMMENTS_COOLDOWN_NAMESPACE=namespace,
        ):
            page = visitor.get(detail_url)
            assert page.status_code == 200
            html = page.content.decode()
            assert 'id="comment-thread"' in html
            assert f'action="{post_url}"' in html
            assert 'maxlength="100"' in html

            invalid = visitor.post(
                post_url,
                {"body": "字" * 101},
                HTTP_HX_REQUEST="true",
            )
            assert invalid.status_code == 422
            assert "字" * 101 in invalid.content.decode()

            created = visitor.post(
                post_url,
                {"body": "只让当前访客看到的缓冲评论"},
                HTTP_HX_REQUEST="true",
            )
            assert created.status_code == 201
            created_html = created.content.decode()
            assert "只让当前访客看到的缓冲评论" in created_html
            assert "等待公开" in created_html
            assert settings.COMMENTS_RECEIPT_COOKIE_NAME in created.cookies

            refreshed = visitor.get(detail_url)
            assert "只让当前访客看到的缓冲评论" in refreshed.content.decode()
            stranger = Client(REMOTE_ADDR="198.51.100.15")
            hidden = stranger.get(detail_url)
            assert "只让当前访客看到的缓冲评论" not in hidden.content.decode()

            session_model = apps.get_model("accounts", "LoginSession")
            owner_token, _ = session_model.issue(account=author, remember=False)
            owner = Client(REMOTE_ADDR="198.51.100.16")
            owner.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = owner_token
            owner_view = owner.get(detail_url)
            assert "只让当前访客看到的缓冲评论" in owner_view.content.decode()

            duplicate = visitor.post(
                post_url,
                {"body": "重复提交"},
                HTTP_HX_REQUEST="true",
            )
            assert duplicate.status_code == 429
            assert int(duplicate.headers["Retry-After"]) >= 1
            assert "请等待" in duplicate.content.decode()
    finally:
        _clear_redis(namespace)


def test_article_comment_login_gate_and_image_upload_partial(tmp_path) -> None:
    namespace = f"kaj-http-cmt002-login-{uuid4()}"
    author = _account("cmt002-http-login", roles=("AUTHOR", "ADMINISTRATOR"))
    member = _account("cmt002-http-member")
    article_id = _published_article(author, post_login_required=True)
    detail_url = reverse("article:detail", kwargs={"article_id": article_id})
    post_url = reverse("article:comment-create", kwargs={"article_id": article_id})
    upload_url = reverse("article:comment-image", kwargs={"article_id": article_id})

    try:
        with override_settings(
            MEDIA_ROOT=tmp_path,
            COMMENTS_COOLDOWN_NAMESPACE=namespace,
        ):
            guest = Client(REMOTE_ADDR="203.0.113.31")
            guest_page = guest.get(detail_url)
            assert guest_page.status_code == 200
            assert "登录后才能发表评论" in guest_page.content.decode()
            assert f'action="{post_url}"' not in guest_page.content.decode()

            denied = guest.post(
                post_url,
                {"body": "访客不能提交"},
                HTTP_HX_REQUEST="true",
            )
            assert denied.status_code == 403

            session_model = apps.get_model("accounts", "LoginSession")
            raw_token, _ = session_model.issue(account=member, remember=False)
            logged_in = Client(REMOTE_ADDR="203.0.113.32")
            logged_in.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = raw_token

            upload = logged_in.post(
                upload_url,
                {
                    "file": SimpleUploadedFile(
                        "comment.png",
                        _png(),
                        content_type="image/png",
                    )
                },
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            assert upload.status_code == 201
            upload_html = upload.content.decode()
            assert 'data-media-upload-result="success"' in upload_html
            assert "data-image-ref=" in upload_html
            image_ref = upload.context["upload"].image_ref

            created = logged_in.post(
                post_url,
                {"body": "登录用户图片评论", "image_ref_1": image_ref},
                HTTP_HX_REQUEST="true",
            )
            assert created.status_code == 201
            comment = apps.get_model("comments", "Comment").objects.get(
                body="登录用户图片评论"
            )
            binding = apps.get_model("media", "MediaBinding").objects.get(
                target_type="comment", target_id=comment.id
            )
            assert comment.author_id == member.id
            assert binding.asset.owner_id == member.id

            page = logged_in.get(detail_url)
            html = page.content.decode()
            assert f'action="{post_url}"' in html
            assert f'data-media-upload-url="{upload_url}"' in html
    finally:
        _clear_redis(namespace)
