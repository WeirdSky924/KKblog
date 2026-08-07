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

from apps.core.ids import new_ulid
from apps.moderation.models import (
    ArticleAppeal,
    ArticleModerationCase,
    DeletedAccountIdentity,
)
from apps.moderation.public import (
    ArticleCaseNotFound,
    article_case_detail,
    article_case_list,
)

Article = apps.get_model("content", "Article")
ArticleRevision = apps.get_model("content", "ArticleRevision")

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str, *, author: bool = False, administrator: bool = False):
    account = apps.get_model("accounts", "Account").objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    roles = apps.get_model("accounts", "RoleAssignment")
    if author or administrator:
        roles.objects.create(account=account, role="AUTHOR")
    if administrator:
        roles.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _client(account=None, *, address: str) -> Client:
    client = Client(REMOTE_ADDR=address)
    if account is not None:
        token, _ = apps.get_model("accounts", "LoginSession").issue(
            account=account,
            remember=False,
        )
        client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token
    return client


def _article(author):
    article = Article.objects.create(author=author, row_version=1)
    revision = ArticleRevision.objects.create(
        article=article,
        sequence=1,
        content_format="MARKDOWN",
        title="HTTP 文章案件",
        body_markdown="HTTP 入口不应复制正文",
        summary_mode="AUTO",
        visibility="AUTHENTICATED",
        created_by=author,
    )
    published_at = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
    Article.objects.filter(pk=article.id).update(
        publication_state="PUBLISHED",
        working_revision_id=revision.id,
        published_revision_id=revision.id,
        published_at=published_at,
        last_published_at=published_at,
    )
    article.refresh_from_db()
    return article


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 12), "#397f91").save(output, format="PNG")
    return output.getvalue()


def test_article_case_http_enforces_four_identities_and_reads_back_db(
    tmp_path,
) -> None:
    administrator = _account("cmt011-http-admin", administrator=True)
    author = _account("cmt011-http-author", author=True)
    user = _account("cmt011-http-user")
    article = _article(author)
    clients = {
        "visitor": _client(address="198.51.100.221"),
        "user": _client(user, address="198.51.100.222"),
        "author": _client(author, address="198.51.100.223"),
        "admin": _client(administrator, address="198.51.100.224"),
    }
    create_url = reverse(
        "admin:article-case-create",
        kwargs={"article_id": article.id},
    )

    for identity in ("visitor", "user", "author"):
        response = clients[identity].post(
            create_url,
            {"action": "HIDE", "reason": "伪造管理动作"},
        )
        assert response.status_code == 403
        assert not ArticleModerationCase.objects.exists()

    created = clients["admin"].post(
        create_url,
        {"action": "HIDE", "reason": "违反内容规范"},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    case = ArticleModerationCase.objects.get(pk=case_id)
    assert (case.article_id, case.author_id, case.state) == (
        article.id,
        author.id,
        "ACTIVE",
    )

    with pytest.raises(ArticleCaseNotFound):
        article_case_detail(actor_id=user.id, case_id=case.id)
    author_detail = article_case_detail(actor_id=author.id, case_id=case.id)
    admin_detail = article_case_detail(actor_id=administrator.id, case_id=case.id)
    assert author_detail.reason == admin_detail.reason == "违反内容规范"
    assert article_case_list(actor_id=administrator.id)[0].id == case.id
    with pytest.raises(PermissionError):
        article_case_list(actor_id=user.id)

    upload_url = reverse(
        "moderation:article-appeal-evidence-upload",
        kwargs={"case_id": case.id},
    )
    appeal_url = reverse(
        "moderation:article-appeal-create",
        kwargs={"case_id": case.id},
    )
    assert clients["visitor"].post(upload_url).status_code == 403
    with override_settings(MEDIA_ROOT=tmp_path):
        upload = clients["author"].post(
            upload_url,
            {
                "file": SimpleUploadedFile(
                    "appeal.png",
                    _png(),
                    content_type="image/png",
                )
            },
        )
    assert upload.status_code == 201
    evidence_ref = upload.json()["evidence_ref"]

    for identity in ("visitor", "user", "admin"):
        response = clients[identity].post(
            appeal_url,
            {"statement": "伪造文章申诉"},
        )
        assert response.status_code == 403
        assert not ArticleAppeal.objects.exists()

    appealed = clients["author"].post(
        appeal_url,
        {
            "statement": "请复核文章隐藏动作",
            "evidence_ref_1": evidence_ref,
        },
    )
    assert appealed.status_code == 201
    appeal_id = appealed.json()["appeal_id"]
    assert ArticleAppeal.objects.get(pk=appeal_id).state == "PENDING"
    case.refresh_from_db()
    assert case.state == "APPEALED"

    review_url = reverse(
        "admin:article-appeal-review",
        kwargs={"appeal_id": appeal_id},
    )
    for identity in ("visitor", "user", "author"):
        response = clients[identity].post(
            review_url,
            {"outcome": "GRANTED", "decision_reason": "伪造终局复审"},
        )
        assert response.status_code == 403
        assert ArticleAppeal.objects.get(pk=appeal_id).state == "PENDING"

    reviewed = clients["admin"].post(
        review_url,
        {"outcome": "GRANTED", "decision_reason": "确认恢复"},
    )
    assert reviewed.status_code == 200
    case.refresh_from_db()
    appeal = ArticleAppeal.objects.get(pk=appeal_id)
    assert (case.state, appeal.state) == ("FINAL_REJECTED", "FINAL_REJECTED")
    assert (
        article_case_detail(
            actor_id=administrator.id,
            case_id=case.id,
        ).appeal.decision_reason
        == "确认恢复"
    )

    second_article = _article(author)
    second_case_id = (
        clients["admin"]
        .post(
            reverse(
                "admin:article-case-create",
                kwargs={"article_id": second_article.id},
            ),
            {"action": "HIDE", "reason": "主动恢复前隐藏"},
        )
        .json()["case_id"]
    )
    restore_url = reverse(
        "admin:article-case-restore",
        kwargs={"case_id": second_case_id},
    )
    for identity in ("visitor", "user", "author"):
        response = clients[identity].post(restore_url)
        assert response.status_code == 403
        assert ArticleModerationCase.objects.get(pk=second_case_id).state == "ACTIVE"
    restored = clients["admin"].post(restore_url)
    assert restored.status_code == 200
    assert ArticleModerationCase.objects.get(pk=second_case_id).state == "RESTORED"


def test_article_case_queries_preserve_deleted_author_identity() -> None:
    administrator = _account("cmt011-query-admin", administrator=True)
    author = _account("cmt011-query-author", author=True)
    article = _article(author)
    response = _client(administrator, address="198.51.100.225").post(
        reverse("admin:article-case-create", kwargs={"article_id": article.id}),
        {"action": "HIDE", "reason": "关闭前案件"},
    )
    case = ArticleModerationCase.objects.get(pk=response.json()["case_id"])
    deletion_id = new_ulid()
    deleted_at = datetime(2026, 7, 25, 7, 0, tzinfo=UTC)
    DeletedAccountIdentity.objects.create(
        account_id=author.id,
        deletion_id=deletion_id,
        deleted_at=deleted_at,
    )
    ArticleModerationCase.objects.filter(pk=case.id).update(
        state="CLOSED",
        resolved_by_id=administrator.id,
        resolved_at=deleted_at,
        closure_reason="ACCOUNT_DELETED",
        closure_deletion_id=deletion_id,
    )

    with pytest.raises(ArticleCaseNotFound):
        article_case_detail(actor_id=author.id, case_id=case.id)
    detail = article_case_detail(actor_id=administrator.id, case_id=case.id)
    item = article_case_list(actor_id=administrator.id, state="CLOSED")[0]
    assert detail.author_deleted is True
    assert detail.author_deletion_id == item.author_deletion_id == deletion_id
    assert detail.author_deleted_at == deleted_at
