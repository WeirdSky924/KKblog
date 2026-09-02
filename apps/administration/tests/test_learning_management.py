from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Account, LoginSession, RoleAssignment
from apps.core.observability.trace import new_trace_code
from apps.learning.models import (
    KnowledgeDocument,
    LearningDailyUsage,
    LearningQuotaPolicy,
)
from apps.learning.public import (
    KnowledgeDocumentAccessPurpose,
    admin_learning_document_detail,
    read_knowledge_document_text,
)
from apps.learning.tests.test_account_documents_backend import _approved
from apps.learning.tests.test_documents_lifecycle import _account
from apps.media.storage import FilesystemMediaStorage

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def quota_policy():
    LearningQuotaPolicy.objects.update_or_create(
        pk=1,
        defaults={
            "daily_uploads": 10,
            "pending_reviews": 3,
            "daily_generations": 5,
            "concurrent_model_runs": 1,
            "unpurged_banks": 100,
            "row_version": 1,
        },
    )


def _client(*, administrator: bool) -> tuple[Client, Account]:
    client = Client()
    account = Account.objects.create_account(
        email=f"learning-admin-http-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    if administrator:
        RoleAssignment.objects.create(
            account=account,
            role=RoleAssignment.Role.ADMINISTRATOR,
        )
    token, _ = LoginSession.issue(
        account=account,
        remember=False,
        client_ip="127.0.0.1",
    )
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token
    return client, account


def test_learning_admin_routes_are_admin_only_and_navigation_is_registered() -> None:
    ordinary, _ = _client(administrator=False)
    assert ordinary.get(reverse("admin:learning-documents")).status_code == 403
    assert ordinary.get(reverse("admin:question-banks")).status_code == 403

    client, _ = _client(administrator=True)
    documents = client.get(reverse("admin:learning-documents"))
    banks = client.get(reverse("admin:question-banks"))
    assert documents.status_code == 200
    assert banks.status_code == 200
    assert "知识文档与申诉" in documents.content.decode()
    assert "题库与运行" in banks.content.decode()


def test_site_quota_form_uses_row_version_and_persists(client) -> None:
    client, _ = _client(administrator=True)
    response = client.post(
        reverse("admin:question-banks"),
        {
            "action": "learning_site_quota",
            "daily_uploads": "12",
            "pending_reviews": "4",
            "daily_generations": "6",
            "concurrent_model_runs": "2",
            "unpurged_banks": "120",
            "max_questions_per_volume": "24",
            "expected_version": "1",
        },
    )
    assert response.status_code == 302
    policy = LearningQuotaPolicy.objects.get(pk=1)
    assert policy.daily_uploads == 12
    assert policy.max_questions_per_volume == 24
    assert policy.row_version == 2


def test_site_quota_form_can_keep_existing_question_limit_when_blank(client) -> None:
    LearningQuotaPolicy.objects.filter(pk=1).update(max_questions_per_volume=18)
    client, _ = _client(administrator=True)
    response = client.post(
        reverse("admin:question-banks"),
        {
            "action": "learning_site_quota",
            "daily_uploads": "12",
            "pending_reviews": "4",
            "daily_generations": "6",
            "concurrent_model_runs": "2",
            "unpurged_banks": "120",
            "max_questions_per_volume": "",
            "expected_version": "1",
        },
    )
    assert response.status_code == 302
    policy = LearningQuotaPolicy.objects.get(pk=1)
    assert policy.max_questions_per_volume == 18


def test_daily_generation_reset_is_available_in_quota_configuration() -> None:
    from django.utils import timezone

    client, _administrator = _client(administrator=True)
    owner = _account("learning-admin-reset-owner")
    usage = LearningDailyUsage.objects.create(
        account=owner,
        usage_date=timezone.localdate(),
        generations_accepted=4,
    )

    page = client.get(reverse("admin:question-banks"))
    assert page.status_code == 200
    assert "重置今日生成计数" in page.content.decode()

    dialog = client.get(
        reverse("admin:question-banks"),
        {"dialog": "learning-generation-reset"},
    )
    assert dialog.status_code == 200
    assert "确认重置今日生成计数" in dialog.content.decode()

    response = client.post(
        reverse("admin:question-banks"),
        {
            "action": "learning_generation_reset",
            "confirm": "learning_generation_reset",
        },
    )
    assert response.status_code == 302
    usage.refresh_from_db()
    assert usage.generations_accepted == 0
    assert usage.row_version == 2


def test_document_batch_preflight_requires_explicit_ids_and_can_execute(
    isolated_media_root,
) -> None:
    client, _ = _client(administrator=True)
    owner = _account("learning-admin-http-owner")
    submitted, _, _ = _approved(
        isolated_media_root,
        owner,
        key="learning-admin-http-document",
    )
    document = KnowledgeDocument.objects.get(pk=submitted.document_id)
    query = {
        "batch_action": "HIDE",
        "selected": f"{document.id}:{document.row_version}",
    }
    preview = client.get(reverse("admin:learning-documents"), query)
    body = preview.content.decode()
    assert preview.status_code == 200
    assert "确认批量处置 1 项" in body
    assert "当前页全部" not in body

    executed = client.post(
        reverse("admin:learning-documents"),
        {
            "action": "learning_batch_execute",
            "target_type": "DOCUMENT",
            "batch_action": "HIDE",
            "targets": f"{document.id}:{document.row_version}",
            "reason_code": "policy_review",
            "confirm": "learning_batch",
        },
    )
    assert executed.status_code == 302
    document.refresh_from_db()
    assert document.admin_hidden_at is not None


def test_document_detail_reads_source_only_on_explicit_dialog_and_records_access(
    isolated_media_root,
) -> None:
    client, administrator = _client(administrator=True)
    owner = _account("learning-admin-http-reader")
    submitted, _, _ = _approved(
        isolated_media_root,
        owner,
        key="learning-admin-http-reader",
        content="# Private source\nSensitive body\n",
    )
    list_response = client.get(reverse("admin:learning-documents"))
    assert "Sensitive body" not in list_response.content.decode()
    direct = read_knowledge_document_text(
        actor_id=administrator.id,
        document_id=submitted.document_id,
        purpose=KnowledgeDocumentAccessPurpose.ADMIN_REVIEW,
        trace_code=new_trace_code(),
        storage=FilesystemMediaStorage(isolated_media_root),
    )
    assert "Sensitive body" in direct.content
    assert (
        admin_learning_document_detail(
            actor_id=administrator.id,
            document_id=submitted.document_id,
        ).item.document_id
        == submitted.document_id
    )

    detail = client.get(
        reverse("admin:learning-documents"),
        {"dialog": "document", "document_id": str(submitted.document_id)},
    )
    assert detail.status_code == 200
    assert "Sensitive body" in detail.content.decode()
    access = apps.get_model("learning", "KnowledgeDocumentAccess").objects.filter(
        document_id=submitted.document_id,
        administrator_actor_id=administrator.id,
    )
    assert access.count() == 2
    assert set(access.values_list("purpose", flat=True)) == {"ADMIN_REVIEW"}
