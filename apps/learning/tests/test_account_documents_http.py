import json
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.learning.public import CURRENT_UPLOAD_STATEMENT_VERSION

from .test_account_documents_backend import _rejected
from .test_documents_lifecycle import _account

pytestmark = pytest.mark.django_db(transaction=True)


def _authenticate(client, account) -> None:
    session_model = apps.get_model("accounts", "LoginSession")
    raw_token, _ = session_model.issue(account=account, remember=False)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = raw_token


def test_documents_page_and_personal_menu_follow_capability(
    client,
) -> None:
    url = reverse("learning:documents")
    visitor = client.get(url)
    assert visitor.status_code == 302
    assert reverse("accounts:login") in visitor.headers["Location"]

    plain = apps.get_model("accounts", "Account").objects.create_account(
        email=f"documents-plain-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    _authenticate(client, plain)
    assert client.get(url).status_code == 404
    settings_page = client.get(reverse("accounts:settings"))
    assert "知识文档" not in settings_page.content.decode("utf-8")

    role_model = apps.get_model("accounts", "RoleAssignment")
    role_model.objects.create(account=plain, role="ADMINISTRATOR")
    assert client.get(url).status_code == 404
    assert "知识文档" not in client.get(reverse("accounts:settings")).content.decode(
        "utf-8"
    )

    role_model.objects.create(account=plain, role="AUTHOR")
    plain.attachment_upload_enabled = True
    plain.save(update_fields=("attachment_upload_enabled", "updated_at"))
    assert client.get(url).status_code == 200
    assert reverse("learning:documents") in client.get(
        reverse("accounts:settings")
    ).content.decode("utf-8")

    owner = _account("documents-owner")
    _authenticate(client, owner)
    response = client.get(url)
    html = response.content.decode("utf-8")
    assert response.status_code == 200
    assert "我的知识文档" in html
    assert "上传 Markdown" in html
    assert "Endpoint" not in html and "Prompt" not in html
    settings_page = client.get(reverse("accounts:settings"))
    assert reverse("learning:documents") in settings_page.content.decode("utf-8")


def test_upload_statement_error_preserves_asset_then_submit_updates_workspace(
    client,
    isolated_media_root,
    monkeypatch,
) -> None:
    owner = _account("documents-submit")
    _authenticate(client, owner)
    monkeypatch.setattr(
        "apps.learning.presentation.account.dispatch_knowledge_review",
        lambda _run_id: None,
    )
    upload = client.post(
        reverse("media:upload", kwargs={"adapter": "knowledge-document"}),
        {
            "file": SimpleUploadedFile(
                "browser.md",
                b"# Browser knowledge\n\nPersistent content.\n",
                "text/markdown",
            )
        },
    )
    assert upload.status_code == 201
    asset = apps.get_model("media", "MediaAsset").objects.get(owner=owner)
    url = reverse("learning:documents")
    invalid = client.post(
        url,
        {
            "action": "submit",
            "source_asset_id": asset.id,
            "statement_version": CURRENT_UPLOAD_STATEMENT_VERSION,
            "idempotency_key": f"browser:{uuid4()}",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="knowledge-workspace",
    )
    invalid_html = invalid.content.decode("utf-8")
    assert invalid.status_code == 422
    assert "必须明确同意" in invalid_html
    assert f'value="{asset.id}"' in invalid_html
    assert not apps.get_model("learning", "KnowledgeDocument").objects.exists()

    submitted = client.post(
        url,
        {
            "action": "submit",
            "source_asset_id": asset.id,
            "statement_version": CURRENT_UPLOAD_STATEMENT_VERSION,
            "accepted": "on",
            "idempotency_key": f"browser:{uuid4()}",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="knowledge-workspace",
    )
    document = apps.get_model("learning", "KnowledgeDocument").objects.get(owner=owner)
    assert submitted.status_code == 200
    assert submitted.headers["HX-Replace-Url"] == reverse("learning:documents")
    assert document.state == "REVIEW_PENDING"
    assert "等待审核" in submitted.content.decode("utf-8")
    assert 'hx-trigger="every 8s"' in submitted.content.decode("utf-8")
    trigger = json.loads(submitted.headers["HX-Trigger-After-Swap"])
    assert trigger["kaj:feedback"]["level"] == "success"
    assert trigger["kaj:feedback"]["message"] == "知识文档已提交审核"


def test_delete_restore_and_appeal_dialog_actions_update_in_place(
    client,
    isolated_media_root,
    monkeypatch,
) -> None:
    owner = _account("documents-actions")
    _authenticate(client, owner)
    monkeypatch.setattr(
        "apps.learning.presentation.account.dispatch_knowledge_review",
        lambda _run_id: None,
    )
    submitted, _, _ = _rejected(
        isolated_media_root,
        owner,
        key="documents:actions",
    )
    document_model = apps.get_model("learning", "KnowledgeDocument")
    document = document_model.objects.get(pk=submitted.document_id)
    url = reverse("learning:documents")

    dialog = client.get(f"{url}?dialog=appeal&document_id={document.id}")
    assert dialog.status_code == 200
    assert "提交申诉" in dialog.content.decode("utf-8")
    appealed = client.post(
        url,
        {
            "action": "appeal",
            "document_id": str(document.id),
            "expected_version": document.row_version,
            "reason_markdown": "请重新检查这份文档。",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="knowledge-workspace",
    )
    assert appealed.status_code == 200
    assert (
        apps.get_model("learning", "LearningAppeal")
        .objects.filter(
            document=document,
            state="PENDING",
        )
        .exists()
    )

    appeal = apps.get_model("learning", "LearningAppeal").objects.get(
        document=document,
        state="PENDING",
    )
    withdrawn = client.post(
        url,
        {
            "action": "withdraw_appeal",
            "appeal_id": str(appeal.id),
            "expected_version": appeal.row_version,
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="knowledge-workspace",
    )
    assert withdrawn.status_code == 200
    appeal.refresh_from_db()
    assert appeal.state == "WITHDRAWN"

    document.refresh_from_db()
    deleted = client.post(
        url,
        {
            "action": "delete",
            "document_id": str(document.id),
            "expected_version": document.row_version,
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="knowledge-workspace",
    )
    assert deleted.status_code == 200
    document.refresh_from_db()
    assert document.state == "DELETE_PENDING"
    restored = client.post(
        url,
        {
            "action": "restore",
            "document_id": str(document.id),
            "expected_version": document.row_version,
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="knowledge-workspace",
    )
    assert restored.status_code == 200
    document.refresh_from_db()
    assert document.state == "REJECTED"
