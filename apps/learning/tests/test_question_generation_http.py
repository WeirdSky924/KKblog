import json
from uuid import uuid4

import pytest
from django.apps import apps
from django.urls import reverse

from apps.learning.public import (
    GenerationQuestionTypes,
    create_question_bank_generation_request,
    mark_question_bank_generation_final_failed,
)

from .test_account_documents_backend import _approved
from .test_account_documents_http import _authenticate
from .test_documents_lifecycle import _account
from .test_question_bank_owner_editing import _published
from .test_question_generation_runtime import (
    NOW,
    _configure_limit,
    _configured_generation_profile,
)

pytestmark = pytest.mark.django_db(transaction=True)


def test_generation_entry_is_explicitly_unavailable_without_admin_configuration(
    client,
    isolated_media_root,
) -> None:
    owner = _account("generation-http-unavailable")
    _authenticate(client, owner)
    submitted, _, _ = _approved(
        isolated_media_root,
        owner,
        key="document:generation-http-unavailable",
    )
    url = reverse("learning:documents")

    page = client.get(url)
    html = page.content.decode("utf-8")
    assert page.status_code == 200
    assert "生成暂不可用" in html
    assert f"dialog=generate&amp;document_id={submitted.document_id}" not in html
    dialog = client.get(f"{url}?dialog=generate&document_id={submitted.document_id}")
    assert "配置题库" not in dialog.content.decode("utf-8")


def test_approved_document_opens_generation_dialog_without_model_controls(
    client,
    isolated_media_root,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("generation-http-dialog")
    _authenticate(client, owner)
    submitted, _, _ = _approved(
        isolated_media_root,
        owner,
        key="document:generation-http-dialog",
    )
    url = reverse("learning:documents")

    page = client.get(url)
    html = page.content.decode("utf-8")
    assert page.status_code == 200
    assert "生成题库" in html
    assert f"dialog=generate&amp;document_id={submitted.document_id}" in html

    dialog = client.get(f"{url}?dialog=generate&document_id={submitted.document_id}")
    dialog_html = dialog.content.decode("utf-8")
    assert dialog.status_code == 200
    assert "配置题库" in dialog_html
    assert 'name="base_title"' in dialog_html
    assert 'name="description"' in dialog_html
    assert 'name="single_choice"' in dialog_html
    assert 'name="multiple_choice"' in dialog_html
    assert 'name="true_false"' in dialog_html
    assert 'name="short_answer"' in dialog_html
    assert "max_questions_per_volume" not in dialog_html
    assert "Endpoint" not in dialog_html
    assert "Prompt" not in dialog_html
    assert 'name="model"' not in dialog_html


def test_generate_action_persists_pending_series_and_updates_workspace(
    client,
    isolated_media_root,
    monkeypatch,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("generation-http-submit")
    _authenticate(client, owner)
    submitted, _, _ = _approved(
        isolated_media_root,
        owner,
        key="document:generation-http-submit",
    )
    calls = []
    monkeypatch.setattr(
        "apps.learning.presentation.account.dispatch_question_generation",
        lambda series_id: calls.append(series_id),
    )
    url = reverse("learning:documents")

    response = client.post(
        url,
        {
            "action": "generate",
            "document_id": str(submitted.document_id),
            "base_title": "Python 面试知识",
            "description": "覆盖文档内的重要知识点。",
            "single_choice": "on",
            "true_false": "on",
            "idempotency_key": f"generation:http:{uuid4()}",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="knowledge-workspace",
    )

    series = apps.get_model("learning", "QuestionBankSeries").objects.get(owner=owner)
    html = response.content.decode("utf-8")
    assert response.status_code == 200
    assert calls == [str(series.id)]
    assert series.source_document_id == submitted.document_id
    assert series.base_title == "Python 面试知识"
    assert series.allowed_question_types == ["SINGLE_CHOICE", "TRUE_FALSE"]
    assert series.max_questions_per_volume_snapshot == 4
    assert series.generation_snapshot_invocation_id
    assert "等待生成" in html
    assert 'hx-trigger="every 8s"' in html
    trigger = json.loads(response.headers["HX-Trigger-After-Swap"])
    assert trigger["kaj:feedback"]["message"] == "题库生成任务已提交"

    polled = client.get(
        url,
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="knowledge-workspace",
    )
    polled_html = polled.content.decode("utf-8")
    assert polled.status_code == 200
    assert "<!doctype html>" not in polled_html
    assert 'id="knowledge-workspace"' in polled_html


def test_generation_validation_preserves_dialog_and_duplicate_submit_is_idempotent(
    client,
    isolated_media_root,
    monkeypatch,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("generation-http-validation")
    _authenticate(client, owner)
    submitted, _, _ = _approved(
        isolated_media_root,
        owner,
        key="document:generation-http-validation",
    )
    url = reverse("learning:documents")
    key = f"generation:http-validation:{uuid4()}"
    base = {
        "action": "generate",
        "document_id": str(submitted.document_id),
        "base_title": "校验题库",
        "description": "保留输入。",
        "idempotency_key": key,
    }
    invalid = client.post(
        url,
        base,
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="knowledge-workspace",
    )
    invalid_html = invalid.content.decode("utf-8")
    assert invalid.status_code == 422
    assert "至少选择一种题型" in invalid_html
    assert 'id="knowledge-generate-dialog"' in invalid_html
    assert f'value="{key}"' in invalid_html
    assert not apps.get_model("learning", "QuestionBankSeries").objects.exists()

    calls = []
    monkeypatch.setattr(
        "apps.learning.presentation.account.dispatch_question_generation",
        lambda series_id: calls.append(series_id),
    )
    valid = {**base, "single_choice": "on"}
    first = client.post(
        url,
        valid,
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="knowledge-workspace",
    )
    repeated = client.post(
        url,
        valid,
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="knowledge-workspace",
    )
    series_model = apps.get_model("learning", "QuestionBankSeries")
    series = series_model.objects.get(owner=owner)
    usage = apps.get_model("learning", "LearningDailyUsage").objects.get(
        account=owner,
        generations_accepted__gt=0,
    )
    assert first.status_code == repeated.status_code == 200
    assert series_model.objects.filter(owner=owner).count() == 1
    assert usage.generations_accepted == 1
    assert calls == [str(series.id)]


def test_published_result_renders_coverage_and_lazy_edit_dialogs(
    client,
    isolated_media_root,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("generation-http-published")
    _authenticate(client, owner)
    series = _published(isolated_media_root, owner, key="http-published")
    bank = series.banks.get(volume_number=1)
    url = reverse("learning:documents")

    page = client.get(url)
    html = page.content.decode("utf-8")
    assert page.status_code == 200
    assert "已发布" in html
    assert "已覆盖" in html and "遗漏" in html
    assert "编辑资料" in html and "查看题目" in html
    assert str(bank.id) in html

    metadata = client.get(f"{url}?dialog=series&series_id={series.id}")
    metadata_html = metadata.content.decode("utf-8")
    assert metadata.status_code == 200
    assert "编辑题库资料" in metadata_html
    assert 'name="tags"' in metadata_html

    bank_dialog = client.get(f"{url}?dialog=bank&bank_id={bank.id}")
    bank_html = bank_dialog.content.decode("utf-8")
    assert bank_dialog.status_code == 200
    assert "当前修订" in bank_html
    assert "变量绑定的是什么?" in bank_html

    question_dialog = client.get(
        f"{url}?dialog=question&bank_id={bank.id}&question_id=q-1"
    )
    question_html = question_dialog.content.decode("utf-8")
    assert question_dialog.status_code == 200
    assert "编辑题目" in question_html
    assert 'name="stem_markdown"' in question_html
    assert 'name="options_text"' in question_html
    assert 'name="revision_reason"' in question_html


def test_metadata_and_question_edits_update_workspace_and_revision(
    client,
    isolated_media_root,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("generation-http-edit")
    _authenticate(client, owner)
    series = _published(isolated_media_root, owner, key="http-edit")
    bank = series.banks.get(volume_number=1)
    url = reverse("learning:documents")

    metadata = client.post(
        url,
        {
            "action": "update_series",
            "series_id": str(series.id),
            "expected_version": series.row_version,
            "base_title": "Python 核心面试",
            "description": "更新后的简介。",
            "tags": "Python\n面试",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="knowledge-workspace",
    )
    assert metadata.status_code == 200
    series.refresh_from_db()
    assert series.base_title == "Python 核心面试"
    assert "Python 核心面试" in metadata.content.decode("utf-8")

    bank.refresh_from_db()
    revised = client.post(
        url,
        {
            "action": "revise_question",
            "bank_id": str(bank.id),
            "logical_id": "q-1",
            "expected_bank_version": bank.row_version,
            "stem_markdown": "变量名绑定到什么?",
            "options_text": "a | 名称\nb | 对象",
            "correct_option_ids": "b",
            "boolean_answer": "",
            "reference_answer": "",
            "scoring_points": "",
            "explanation_markdown": "变量名绑定到对象。",
            "revision_reason": "修正题干",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="knowledge-workspace",
    )
    assert revised.status_code == 200
    bank.refresh_from_db()
    assert bank.current_revision.sequence == 2
    assert bank.current_revision.questions.get(logical_id="q-1").stem_markdown == (
        "变量名绑定到什么?"
    )
    trigger = json.loads(revised.headers["HX-Trigger-After-Swap"])
    assert trigger["kaj:feedback"]["message"] == "题目修订已保存"


def test_failed_generation_retry_creates_new_pending_series_in_place(
    client,
    isolated_media_root,
    monkeypatch,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("generation-http-retry")
    _authenticate(client, owner)
    document, _, _ = _approved(
        isolated_media_root,
        owner,
        key="document:generation-http-retry",
    )
    first = create_question_bank_generation_request(
        owner_id=owner.id,
        document_id=document.document_id,
        base_title="失败题库",
        description="",
        question_types=GenerationQuestionTypes(single_choice=True),
        idempotency_key="generation:http-retry:first",
        dispatcher=lambda _series_id: None,
        now=NOW,
    )
    mark_question_bank_generation_final_failed(
        series_id=first.series_id,
        safe_error_code="agents.provider_failed.v1",
        completed_at=NOW,
    )
    failed = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=first.series_id
    )
    calls = []
    monkeypatch.setattr(
        "apps.learning.presentation.account.dispatch_question_generation",
        lambda series_id: calls.append(series_id),
    )
    url = reverse("learning:documents")

    response = client.post(
        url,
        {
            "action": "retry_generation",
            "series_id": str(failed.id),
            "expected_version": failed.row_version,
            "idempotency_key": f"generation:http-retry:{uuid4()}",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="knowledge-workspace",
    )

    assert response.status_code == 200
    assert (
        apps.get_model("learning", "QuestionBankSeries")
        .objects.filter(owner=owner)
        .count()
        == 2
    )
    replacement = (
        apps.get_model("learning", "QuestionBankSeries")
        .objects.exclude(pk=failed.id)
        .get()
    )
    assert calls == [str(replacement.id)]
    assert replacement.state == "GENERATION_PENDING"
    assert "等待生成" in response.content.decode("utf-8")
