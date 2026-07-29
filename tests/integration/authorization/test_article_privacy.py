from datetime import timedelta
from uuid import uuid4

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.content.models import AdminArticleViewReceipt, Article, ArticleRevision
from apps.content.public import (
    ArticleSnapshot,
    ContentFormat,
    Visibility,
    create_article,
    create_section,
    prepare_publication,
    publish_article,
)
from apps.core.events.models import OutboxEvent
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code

from .conftest import IdentityMatrix

pytestmark = pytest.mark.django_db(transaction=True)


def _draft(
    identities: IdentityMatrix,
    *,
    owner=None,
    visibility: Visibility = Visibility.PUBLIC,
    title: str = "授权矩阵文章",
):
    owner = owner or identities.owner
    section = create_section(
        actor_id=identities.admin.id,
        name=f"QA002-{uuid4()}",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    return create_article(
        actor_id=owner.id,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.MARKDOWN,
            title=title,
            body="授权矩阵正文",
            section_id=section.section_id,
            visibility=visibility,
        ),
        capacity_check=lambda: None,
    )


def _published(identities: IdentityMatrix, **kwargs):
    draft = _draft(identities, **kwargs)
    review = prepare_publication(
        actor_id=(kwargs.get("owner") or identities.owner).id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
    )
    publish_article(
        actor_id=(kwargs.get("owner") or identities.owner).id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
    )
    return draft


def test_published_article_http_visibility_matrix_and_privacy_404(
    identities: IdentityMatrix,
) -> None:
    public = _published(identities, visibility=Visibility.PUBLIC, title="大众文章")
    authenticated = _published(
        identities,
        visibility=Visibility.AUTHENTICATED,
        title="登录文章",
    )
    private = _published(
        identities,
        visibility=Visibility.PRIVATE,
        title="不可泄露的私人标题",
    )

    public_url = reverse("article:detail", args=(public.article_id,))
    for identity, client in identities.clients.items():
        assert client.get(public_url).status_code == 200, identity

    authenticated_url = reverse("article:detail", args=(authenticated.article_id,))
    reminder = identities.clients["visitor"].get(authenticated_url)
    assert reminder.status_code == 200
    assert "这篇文章需要登录后查看" in reminder.content.decode()
    for identity in ("user", "owner", "other_author", "admin"):
        assert identities.clients[identity].get(authenticated_url).status_code == 200

    private_url = reverse("article:detail", args=(private.article_id,))
    assert identities.clients["owner"].get(private_url).status_code == 200
    for identity in ("visitor", "user", "other_author", "admin"):
        denied = identities.clients[identity].get(private_url)
        assert denied.status_code == 404, identity
        body = denied.content.decode()
        assert "不可泄露的私人标题" not in body
        assert "未找到请求的内容" in body
    unknown = identities.clients["user"].get(
        reverse("article:detail", args=(new_ulid(),))
    )
    assert unknown.status_code == 404
    unknown_body = unknown.content.decode()
    assert "未找到请求的内容" in unknown_body
    assert "不可泄露的私人标题" not in unknown_body


def test_draft_scheduled_and_cooling_articles_do_not_leak_to_reader_routes(
    identities: IdentityMatrix,
) -> None:
    draft = _draft(identities, title="草稿秘密")
    scheduled = _draft(identities, title="排期秘密")
    scheduled_row = Article.objects.get(pk=scheduled.article_id)
    now = timezone.now()
    Article.objects.filter(pk=scheduled.article_id).update(
        publication_state=Article.PublicationState.SCHEDULED,
        scheduled_revision_id=scheduled.revision_id,
        scheduled_at=now,
        scheduled_for=now + timedelta(days=1),
    )
    deleted = _published(identities, title="删除冷静期秘密")
    Article.objects.filter(pk=deleted.article_id).update(
        deleted_at=now,
        purge_after=now + timedelta(days=7),
    )

    for article_id in (draft.article_id, scheduled_row.id, deleted.article_id):
        url = reverse("article:detail", args=(article_id,))
        for identity in identities.clients:
            response = identities.clients[identity].get(url)
            assert response.status_code == 404, (article_id, identity)


def test_admin_uses_explicit_read_only_route_and_daily_notification_dedupe(
    identities: IdentityMatrix,
) -> None:
    private = _published(
        identities,
        visibility=Visibility.PRIVATE,
        title="管理员只读私人文章",
    )
    url = reverse("admin:articles")
    for _attempt in range(2):
        response = identities.clients["admin"].get(
            url,
            {"detail": private.article_id, "revision": "working"},
        )
        assert response.status_code == 200
        assert "管理员只读私人文章" in response.content.decode()

    assert (
        AdminArticleViewReceipt.objects.filter(
            administrator=identities.admin,
            author=identities.owner,
            article_id=private.article_id,
        ).count()
        == 1
    )
    assert (
        OutboxEvent.objects.filter(
            event_type="article.admin_viewed.v1",
            aggregate_id=private.article_id,
        ).count()
        == 1
    )


@pytest.mark.parametrize(
    "route_name",
    ("authoring:edit", "authoring:review", "authoring:versions"),
)
def test_authoring_object_routes_hide_other_authors_article(
    identities: IdentityMatrix,
    route_name: str,
) -> None:
    article = _draft(identities)
    url = reverse(route_name, args=(article.article_id,))
    assert identities.clients["owner"].get(url).status_code == 200
    assert identities.clients["user"].get(url).status_code == 403
    assert identities.clients["other_author"].get(url).status_code == 404
    assert identities.clients["admin"].get(url).status_code == 404


def test_forged_editor_post_cannot_create_revision_for_another_author(
    identities: IdentityMatrix,
) -> None:
    article = _draft(identities)
    url = reverse("authoring:edit", args=(article.article_id,))
    before = ArticleRevision.objects.filter(article_id=article.article_id).count()
    payload = {
        "content_format": "MARKDOWN",
        "upload_scope": new_ulid(),
        "baseline_revision_id": article.revision_id,
        "edit_token": "forged.token",
        "title": "越权修改",
        "body": "不能写入",
        "summary_mode": "AUTO",
        "visibility": "PUBLIC",
        "comments_enabled": "on",
    }
    for identity, expected in (
        ("user", 403),
        ("other_author", 404),
        ("admin", 404),
    ):
        assert identities.clients[identity].post(url, payload).status_code == expected
        assert (
            identities.clients[identity]
            .post(url, payload, HTTP_HX_REQUEST="true")
            .status_code
            == expected
        )
    assert (
        ArticleRevision.objects.filter(article_id=article.article_id).count() == before
    )


def test_admin_authoring_own_article_uses_author_semantics(
    identities: IdentityMatrix,
) -> None:
    own = _draft(identities, owner=identities.admin, title="管理员自己的草稿")
    assert (
        identities.clients["admin"]
        .get(reverse("authoring:edit", args=(own.article_id,)))
        .status_code
        == 200
    )
    assert not AdminArticleViewReceipt.objects.filter(
        article_id=own.article_id
    ).exists()
