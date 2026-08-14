from dataclasses import dataclass
from uuid import uuid4

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Account, LoginSession, RoleAssignment
from apps.content.models import Article
from apps.content.public import (
    ArticleSnapshot,
    ContentFormat,
    create_article,
    create_section,
    prepare_publication,
    publish_article,
    save_revision,
)
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code

pytestmark = pytest.mark.django_db(transaction=True)


@dataclass(frozen=True, slots=True)
class PreviewSetup:
    admin: Account
    author: Account
    admin_client: Client
    user_client: Client
    article_id: str
    first_revision_id: str
    latest_revision_id: str


def _account(label: str, *, author: bool = False, administrator: bool = False):
    account = Account.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    if author or administrator:
        RoleAssignment.objects.create(account=account, role="AUTHOR")
    if administrator:
        RoleAssignment.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _client(account: Account, address: str) -> Client:
    token, _session = LoginSession.issue(
        account=account,
        remember=False,
        client_ip=address,
    )
    client = Client(REMOTE_ADDR=address)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token
    return client


def _publish(author: Account, article_id: str, revision_id: str) -> None:
    article = Article.objects.get(pk=article_id)
    review = prepare_publication(
        actor_id=author.id,
        article_id=article_id,
        revision_id=revision_id,
        expected_row_version=article.row_version,
    )
    publish_article(
        actor_id=author.id,
        article_id=article_id,
        revision_id=revision_id,
        expected_row_version=article.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
    )


def _setup() -> PreviewSetup:
    admin = _account("preview-admin", administrator=True)
    author = _account("preview-author", author=True)
    user = _account("preview-user")
    section = create_section(
        actor_id=admin.id,
        name=f"预览分区-{uuid4()}",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    first = create_article(
        actor_id=author.id,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.MARKDOWN,
            title="管理预览第一版",
            body="第一版正文",
            section_id=section.section_id,
        ),
        capacity_check=lambda: None,
    )
    _publish(author, first.article_id, first.revision_id)
    aggregate = Article.objects.get(pk=first.article_id)
    latest = save_revision(
        actor_id=author.id,
        article_id=first.article_id,
        expected_row_version=aggregate.row_version,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.MARKDOWN,
            title="管理预览第二版",
            body="第二版正文",
            section_id=section.section_id,
        ),
        capacity_check=lambda: None,
    )
    _publish(author, first.article_id, latest.revision_id)
    return PreviewSetup(
        admin=admin,
        author=author,
        admin_client=_client(admin, "198.51.100.50"),
        user_client=_client(user, "198.51.100.51"),
        article_id=first.article_id,
        first_revision_id=first.revision_id,
        latest_revision_id=latest.revision_id,
    )


def test_article_list_exposes_htmx_preview_dialog_without_bottom_detail() -> None:
    setup = _setup()
    response = setup.admin_client.get(reverse("admin:articles"))
    body = response.content.decode()

    assert response.status_code == 200
    assert 'id="article-preview-dialog"' in body
    assert 'id="article-preview-content"' in body
    assert "data-article-preview-trigger" in body
    assert reverse("admin:article-preview", args=(setup.article_id,)) in body
    assert "查看工作版本" in body
    assert "查看发布历史" in body
    assert 'id="article-detail"' not in body


def test_preview_partial_switches_published_versions_and_preserves_state() -> None:
    setup = _setup()
    preview_url = reverse("admin:article-preview", args=(setup.article_id,))
    before = Article.objects.values(
        "working_revision_id",
        "published_revision_id",
        "publication_state",
        "row_version",
    ).get(pk=setup.article_id)

    working = setup.admin_client.get(
        preview_url,
        {"revision": "working"},
        HTTP_HX_REQUEST="true",
    )
    working_body = working.content.decode()
    assert working.status_code == 200
    assert "当前工作版本" in working_body
    assert "管理预览第二版" in working_body
    assert "第二版正文" in working_body

    latest = setup.admin_client.get(
        preview_url,
        {"revision": "published"},
        HTTP_HX_REQUEST="true",
    )
    latest_body = latest.content.decode()
    assert latest.status_code == 200
    assert "发布历史" in latest_body
    assert setup.first_revision_id in latest_body
    assert setup.latest_revision_id in latest_body
    assert "管理预览第二版" in latest_body
    assert "第二版正文" in latest_body

    first = setup.admin_client.get(
        preview_url,
        {
            "revision": "published",
            "revision_id": setup.first_revision_id,
        },
        HTTP_HX_REQUEST="true",
    )
    first_body = first.content.decode()
    assert first.status_code == 200
    assert "管理预览第一版" in first_body
    assert "第一版正文" in first_body
    assert 'hx-target="#article-preview-content"' in first_body

    after = Article.objects.values(
        "working_revision_id",
        "published_revision_id",
        "publication_state",
        "row_version",
    ).get(pk=setup.article_id)
    assert after == before


def test_preview_supports_full_page_fallback_and_safe_boundaries() -> None:
    setup = _setup()
    fallback = setup.admin_client.get(
        reverse("admin:articles"),
        {
            "detail": setup.article_id,
            "revision": "published",
            "revision_id": setup.first_revision_id,
        },
    )
    fallback_body = fallback.content.decode()
    assert fallback.status_code == 200
    assert "data-auto-modal" in fallback_body
    assert "管理预览第一版" in fallback_body
    assert "第一版正文" in fallback_body

    preview_url = reverse("admin:article-preview", args=(setup.article_id,))
    denied = setup.user_client.get(
        preview_url,
        {"revision": "working"},
        HTTP_HX_REQUEST="true",
    )
    assert denied.status_code == 403
    unknown = setup.admin_client.get(
        reverse("admin:article-preview", args=(new_ulid(),)),
        {"revision": "working"},
        HTTP_HX_REQUEST="true",
    )
    assert unknown.status_code == 404
    unpublished = setup.admin_client.get(
        preview_url,
        {"revision": "published", "revision_id": new_ulid()},
        HTTP_HX_REQUEST="true",
    )
    assert unpublished.status_code == 404
