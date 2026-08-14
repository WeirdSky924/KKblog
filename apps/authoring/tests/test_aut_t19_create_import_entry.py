from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.core.ids import new_ulid

pytestmark = pytest.mark.django_db(transaction=True)


def _author():
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"create-import-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    role_model.objects.create(account=account, role="AUTHOR")
    return account


def _client(account) -> Client:
    session_model = apps.get_model("accounts", "LoginSession")
    raw_token, _ = session_model.issue(account=account, remember=False)
    client = Client(REMOTE_ADDR="127.0.0.1")
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = raw_token
    return client


def test_create_entry_offers_three_paths_without_a_sixth_workflow_step() -> None:
    response = _client(_author()).get(reverse("authoring:create"))
    html = response.content.decode()

    assert response.status_code == 200
    assert html.count("data-create-mode=") == 3
    assert 'data-create-mode="MARKDOWN"' in html
    assert 'data-create-mode="TIPTAP_JSON"' in html
    assert 'data-create-mode="IMPORT"' in html
    assert f'href="{reverse("authoring:import")}"' in html
    assert "02 / 05" in html
    assert "<strong>导入</strong>" not in html


def test_legacy_import_route_is_presented_as_the_create_stage() -> None:
    response = _client(_author()).get(reverse("authoring:import"))
    html = response.content.decode()

    assert response.status_code == 200
    assert "文章导入" in html
    assert "返回创建方式" in html
    assert "02 / 05" in html
    assert "<strong>导入</strong>" not in html
    assert "data-import-upload-form" in html


@pytest.mark.parametrize(
    ("filename", "expected_kind"),
    (("article.md", "MARKDOWN"), ("articles.zip", "ZIP")),
)
def test_create_import_path_delegates_supported_files_to_exchange_owner(
    monkeypatch,
    filename: str,
    expected_kind: str,
) -> None:
    captured = []
    job_id = new_ulid()

    def create_preview(**kwargs):
        captured.append(kwargs)
        tuple(kwargs["chunks"])
        return SimpleNamespace(job_id=job_id)

    integrations = SimpleNamespace(create_configured_import_preview=create_preview)
    monkeypatch.setattr(
        "apps.authoring.presentation.import_views._integrations",
        lambda: integrations,
    )

    response = _client(_author()).post(
        reverse("authoring:import"),
        {"source": SimpleUploadedFile(filename, b"# Imported article")},
    )

    assert response.status_code == 302
    assert response.url == reverse("authoring:import-job", args=(job_id,))
    assert len(captured) == 1
    assert captured[0]["source_name"] == filename
    assert captured[0]["source_kind"] == expected_kind


def test_create_import_path_keeps_unsupported_file_error_at_the_entry(
    monkeypatch,
) -> None:
    integrations = SimpleNamespace(
        create_configured_import_preview=lambda **kwargs: pytest.fail(
            "unsupported files must not reach exchange"
        )
    )
    monkeypatch.setattr(
        "apps.authoring.presentation.import_views._integrations",
        lambda: integrations,
    )

    response = _client(_author()).post(
        reverse("authoring:import"),
        {"source": SimpleUploadedFile("article.txt", b"plain text")},
    )

    assert response.status_code == 422
    assert "请选择 .md 或 .zip 文件" in response.content.decode()


def _terminal_context(*article_ids: str):
    items = tuple(
        SimpleNamespace(
            item_id=new_ulid(),
            title=f"导入文章 {index}",
            result_status="SUCCESS",
            result_label="成功",
            result_reason_label="已创建文章",
            result_article_id=article_id,
        )
        for index, article_id in enumerate(article_ids, start=1)
    )
    page = SimpleNamespace(
        job_id=new_ulid(),
        status="COMPLETED",
        status_label="导入完成",
        terminal=True,
        processing=False,
        editable=False,
        result_summary={"success": len(items), "skipped": 0, "failed": 0},
        items=items,
    )
    return {
        "import_page": page,
        "import_rows": tuple({"item": item, "form": None} for item in items),
        "import_selected_count": 0,
        "import_confirm_form": None,
        "import_error": "",
    }


def test_single_successful_import_continues_directly_to_edit(monkeypatch) -> None:
    article_id = new_ulid()
    context = _terminal_context(article_id)
    monkeypatch.setattr(
        "apps.authoring.presentation.import_views._context",
        lambda **kwargs: context,
    )
    client = _client(_author())
    job_id = new_ulid()

    full = client.get(reverse("authoring:import-job", args=(job_id,)))
    fragment = client.get(
        reverse("authoring:import-status", args=(job_id,)),
        HTTP_HX_REQUEST="true",
    )
    expected = reverse("authoring:edit", args=(article_id,))

    assert full.status_code == 302
    assert full.url == expected
    assert fragment.status_code == 204
    assert fragment.headers["HX-Redirect"] == expected


def test_multi_article_import_keeps_results_with_edit_actions(monkeypatch) -> None:
    first_id = new_ulid()
    second_id = new_ulid()
    context = _terminal_context(first_id, second_id)
    monkeypatch.setattr(
        "apps.authoring.presentation.import_views._context",
        lambda **kwargs: context,
    )

    response = _client(_author()).get(
        reverse("authoring:import-status", args=(new_ulid(),))
    )
    html = response.content.decode()

    assert response.status_code == 200
    assert html.count("继续编辑") == 2
    assert reverse("authoring:edit", args=(first_id,)) in html
    assert reverse("authoring:edit", args=(second_id,)) in html
