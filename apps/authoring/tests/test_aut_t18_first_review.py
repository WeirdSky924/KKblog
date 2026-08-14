from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.content.public import ContentFormat, create_section
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code

pytestmark = pytest.mark.django_db(transaction=True)


def _author():
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"first-review-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    for role in ("AUTHOR", "ADMINISTRATOR"):
        role_model.objects.create(account=account, role=role)
    return account


def _client(account) -> Client:
    session_model = apps.get_model("accounts", "LoginSession")
    raw_token, _ = session_model.issue(account=account, remember=False)
    client = Client(REMOTE_ADDR="127.0.0.1")
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = raw_token
    return client


def _create_page(client: Client, *, content_format: str = ContentFormat.MARKDOWN):
    return client.get(
        reverse("authoring:create"),
        {"format": content_format},
    )


def _payload(page, **overrides) -> dict[str, str]:
    form = page.context["editor_form"]
    values = {
        "content_format": form["content_format"].value(),
        "upload_scope": form["upload_scope"].value(),
        "baseline_revision_id": form["baseline_revision_id"].value(),
        "edit_token": form["edit_token"].value() or "",
        "title": "首次审查文章",
        "body": "# 正文\n\n直接从新建页面进入终稿审查。",
        "summary_mode": "AUTO",
        "visibility": "PUBLIC",
        "section_id": "",
        "proposed_tag_names": "[]",
        "cover_asset_id": "",
        "attachment_asset_id": "",
        "comments_enabled": "on",
    }
    values.update(overrides)
    return values


def test_create_editor_exposes_first_review_submitter() -> None:
    page = _create_page(_client(_author()))
    html = page.content.decode()

    assert page.status_code == 200
    assert 'data-editor-mode="create"' in html
    assert "data-submit-once" in html
    assert 'name="save_intent"' in html
    assert 'value="review"' in html
    assert "终稿审查" in html


@pytest.mark.parametrize(
    ("content_format", "body"),
    (
        (ContentFormat.MARKDOWN, "# 正文\n\n直接从新建页面进入终稿审查。"),
        (
            ContentFormat.TIPTAP_JSON,
            '{"type":"doc","content":[{"type":"paragraph","content":'
            '[{"type":"text","text":"直接进入终稿审查"}]}]}',
        ),
    ),
)
def test_first_review_creates_one_complete_draft_then_opens_review(
    content_format: str,
    body: str,
) -> None:
    author = _author()
    client = _client(author)
    section = create_section(
        actor_id=author.id,
        name=f"首次审查分区-{uuid4()}",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    page = _create_page(client, content_format=content_format)

    response = client.post(
        reverse("authoring:create"),
        _payload(
            page,
            body=body,
            section_id=str(section.section_id),
            save_intent="review",
        ),
    )

    article_model = apps.get_model("content", "Article")
    revision_model = apps.get_model("content", "ArticleRevision")
    article = article_model.objects.get(author_id=author.id)
    assert response.status_code == 302
    assert response.url == reverse("authoring:review", args=(article.id,))
    assert article_model.objects.filter(author_id=author.id).count() == 1
    assert revision_model.objects.filter(article=article).count() == 1
    assert article.working_revision.title == "首次审查文章"
    assert client.get(response.url).status_code == 200


def test_invalid_first_review_stays_in_editor_without_creating_draft() -> None:
    author = _author()
    client = _client(author)
    page = _create_page(client)

    response = client.post(
        reverse("authoring:create"),
        _payload(page, title="", save_intent="review"),
    )

    assert response.status_code == 422
    assert response.context["editor_form"].errors["title"]
    assert "终稿审查" in response.content.decode()
    assert (
        not apps.get_model("content", "Article")
        .objects.filter(author_id=author.id)
        .exists()
    )


def test_first_review_preserves_draft_when_review_page_rejects_it() -> None:
    author = _author()
    client = _client(author)
    page = _create_page(client)

    saved = client.post(
        reverse("authoring:create"),
        _payload(page, save_intent="review"),
    )
    review = client.get(saved.url)

    article_model = apps.get_model("content", "Article")
    revision_model = apps.get_model("content", "ArticleRevision")
    article = article_model.objects.get(author_id=author.id)
    assert saved.status_code == 302
    assert saved.url == reverse("authoring:review", args=(article.id,))
    assert review.status_code == 422
    assert "暂时不能进入审查" in review.content.decode()
    assert article_model.objects.filter(author_id=author.id).count() == 1
    assert revision_model.objects.filter(article=article).count() == 1


def test_first_review_htmx_uses_the_shared_review_redirect() -> None:
    author = _author()
    client = _client(author)
    page = _create_page(client)

    response = client.post(
        reverse("authoring:create"),
        _payload(page, save_intent="review"),
        HTTP_HX_REQUEST="true",
    )

    article = apps.get_model("content", "Article").objects.get(author_id=author.id)
    assert response.status_code == 204
    assert response.headers["HX-Redirect"] == reverse(
        "authoring:review", args=(article.id,)
    )


def test_create_submitters_send_the_same_snapshot_to_content_owner(monkeypatch) -> None:
    author = _author()
    client = _client(author)
    captured = []
    article_ids = [new_ulid(), new_ulid()]

    def capture_create(*, actor_id, snapshot):
        captured.append((actor_id, snapshot))
        return SimpleNamespace(article_id=article_ids[len(captured) - 1])

    monkeypatch.setattr(
        "apps.authoring.presentation.editor_views.create_article",
        capture_create,
    )
    shared = {
        "title": "等价保存",
        "body": "正文",
        "proposed_tag_names": '["待审核标签"]',
        "cover_asset_id": new_ulid(),
        "attachment_asset_id": new_ulid(),
    }
    normal_page = _create_page(client)
    normal = client.post(
        reverse("authoring:create"),
        _payload(normal_page, **shared),
    )
    review_page = _create_page(client)
    review = client.post(
        reverse("authoring:create"),
        _payload(review_page, save_intent="review", **shared),
    )

    assert normal.status_code == 302
    assert (
        normal.url == f"{reverse('authoring:edit', args=(article_ids[0],))}?created=1"
    )
    assert review.status_code == 302
    assert review.url == reverse("authoring:review", args=(article_ids[1],))
    assert len(captured) == 2
    assert captured[0][0] == captured[1][0] == author.id
    assert captured[0][1] == captured[1][1]
    assert captured[0][1].proposed_tag_names == ("待审核标签",)
    assert captured[0][1].cover_asset_id == shared["cover_asset_id"]
    assert captured[0][1].attachment_asset_id == shared["attachment_asset_id"]
