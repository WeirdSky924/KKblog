from datetime import timedelta

import pytest
from django.apps import apps

from apps.accounts.models import RoleAssignment
from apps.core.events.models import OutboxEvent
from apps.core.observability.trace import new_trace_code
from apps.learning.public import (
    AdminLearningAction,
    AdminLearningTarget,
    LearningAdminTargetType,
    LearningAppealDecision,
    LearningCommandError,
    QuestionBankVisibility,
    admin_learning_appeal_page,
    admin_learning_document_page,
    admin_learning_quota_snapshot,
    admin_question_bank_page,
    administer_knowledge_document,
    administer_question_bank,
    execute_learning_admin_batch,
    preflight_learning_admin_batch,
    review_learning_appeal,
    submit_learning_appeal,
    submit_question_bank_appeal,
)

from .test_account_documents_backend import _administrator, _approved
from .test_documents_lifecycle import NOW, _account
from .test_question_banks_lifecycle import _published
from .test_question_generation_runtime import _configured_generation_profile

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def generation_profile():
    return _configured_generation_profile()


def _meta():
    return {"trace_code": new_trace_code(), "client_ip": "127.0.0.1"}


def _admin_account():
    existing = (
        RoleAssignment.objects.filter(role=RoleAssignment.Role.ADMINISTRATOR)
        .select_related("account")
        .first()
    )
    return existing.account if existing else _administrator("learning-admin")


def test_admin_document_action_is_audited_notified_and_appealable(
    isolated_media_root,
) -> None:
    administrator = _admin_account()
    owner = _account("learning-admin-document-owner")
    submitted, _, _ = _approved(
        isolated_media_root,
        owner,
        key="learning-admin-document",
    )
    document_model = apps.get_model("learning", "KnowledgeDocument")
    document = document_model.objects.get(pk=submitted.document_id)

    hidden = administer_knowledge_document(
        administrator_id=administrator.id,
        document_id=document.id,
        expected_version=document.row_version,
        action=AdminLearningAction.HIDE,
        reason_code="policy_review",
        now=NOW + timedelta(minutes=3),
        **_meta(),
    )

    document.refresh_from_db()
    assert hidden.admin_hidden is True
    assert document.admin_lock_reason == "policy_review"
    assert (
        apps.get_model("operations", "AuditEntry")
        .objects.filter(
            action="learning.document.admin.hide",
            target_id=str(document.id),
        )
        .exists()
    )
    event = OutboxEvent.objects.get(
        event_type="learning.document_administration_changed.v1"
    )
    assert event.payload == {
        "recipient_id": str(owner.id),
        "action": "HIDE",
    }

    appeal = submit_learning_appeal(
        owner_id=owner.id,
        document_id=document.id,
        expected_document_version=document.row_version,
        reason_markdown="请重新检查管理处置。",
        now=NOW + timedelta(minutes=4),
    )
    decided = review_learning_appeal(
        administrator_id=administrator.id,
        appeal_id=appeal.appeal_id,
        expected_version=appeal.row_version,
        decision=LearningAppealDecision.APPROVED,
        decision_markdown="恢复文档使用资格。",
        dispatcher=lambda _run_id: None,
        now=NOW + timedelta(minutes=5),
        **_meta(),
    )

    document.refresh_from_db()
    assert decided.target_type == LearningAdminTargetType.DOCUMENT
    assert document.admin_lock_reason == ""
    assert document.admin_hidden_at is None


def test_admin_bank_action_supports_bank_appeal_and_public_restore(
    isolated_media_root,
) -> None:
    administrator = _admin_account()
    owner = _account("learning-admin-bank-owner")
    bank = _published(isolated_media_root, owner, key="learning-admin-bank")

    hidden = administer_question_bank(
        administrator_id=administrator.id,
        bank_id=bank.id,
        expected_version=bank.row_version,
        action=AdminLearningAction.HIDE,
        reason_code="policy_review",
        now=NOW + timedelta(minutes=3),
        **_meta(),
    )
    assert hidden.state == QuestionBankVisibility.ADMIN_HIDDEN

    bank.refresh_from_db()
    appeal = submit_question_bank_appeal(
        owner_id=owner.id,
        bank_id=bank.id,
        expected_bank_version=bank.row_version,
        reason_markdown="该题库可以公开。",
        now=NOW + timedelta(minutes=4),
    )
    decided = review_learning_appeal(
        administrator_id=administrator.id,
        appeal_id=appeal.appeal_id,
        expected_version=appeal.row_version,
        decision=LearningAppealDecision.APPROVED,
        decision_markdown="恢复公开。",
        dispatcher=lambda _run_id: None,
        now=NOW + timedelta(minutes=5),
        **_meta(),
    )

    bank.refresh_from_db()
    assert decided.target_type == LearningAdminTargetType.QUESTION_BANK
    assert bank.visibility == QuestionBankVisibility.PUBLISHED
    assert bank.admin_lock_reason == ""
    assert (
        apps.get_model("operations", "AuditEntry")
        .objects.filter(
            action="learning.bank.admin.restore",
            target_id=str(bank.id),
        )
        .exists()
    )


def test_explicit_batch_preflight_and_execution_never_expand_selection(
    isolated_media_root,
) -> None:
    administrator = _admin_account()
    owner = _account("learning-admin-batch-owner")
    first, _, _ = _approved(
        isolated_media_root,
        owner,
        key="learning-admin-batch-first",
    )
    second, _, _ = _approved(
        isolated_media_root,
        owner,
        key="learning-admin-batch-second",
        content="# Second\nDifferent knowledge\n",
    )
    model = apps.get_model("learning", "KnowledgeDocument")
    first_row = model.objects.get(pk=first.document_id)
    second_row = model.objects.get(pk=second.document_id)
    selected = (
        AdminLearningTarget(first_row.id, first_row.row_version),
        AdminLearningTarget(second_row.id, second_row.row_version),
    )

    preflight = preflight_learning_admin_batch(
        administrator_id=administrator.id,
        target_type=LearningAdminTargetType.DOCUMENT,
        action=AdminLearningAction.HIDE,
        targets=selected,
    )
    assert preflight.total == 2
    assert preflight.executable == 2
    assert preflight.state_counts == {"APPROVED": 2}

    model.objects.filter(pk=second_row.id).update(
        row_version=second_row.row_version + 1
    )
    result = execute_learning_admin_batch(
        administrator_id=administrator.id,
        target_type=LearningAdminTargetType.DOCUMENT,
        action=AdminLearningAction.HIDE,
        targets=selected,
        reason_code="policy_review",
        now=NOW + timedelta(minutes=3),
        **_meta(),
    )
    assert result.total == 2
    assert result.succeeded == 1
    assert result.failed == 1
    assert model.objects.filter(admin_hidden_at__isnull=False).count() == 1

    with pytest.raises(LearningCommandError):
        preflight_learning_admin_batch(
            administrator_id=administrator.id,
            target_type=LearningAdminTargetType.DOCUMENT,
            action=AdminLearningAction.HIDE,
            targets=(),
        )


def test_admin_queries_are_bounded_and_keep_sensitive_content_out_of_lists(
    isolated_media_root,
) -> None:
    administrator = _admin_account()
    owner = _account("learning-admin-query-owner")
    submitted, _, _ = _approved(
        isolated_media_root,
        owner,
        key="learning-admin-query",
        content="# Private\nSensitive body\n",
    )
    bank = _published(isolated_media_root, owner, key="learning-admin-query-bank")

    documents = admin_learning_document_page(
        actor_id=administrator.id,
        page=1,
        page_size=20,
    )
    banks = admin_question_bank_page(
        actor_id=administrator.id,
        page=1,
        page_size=20,
    )
    appeals = admin_learning_appeal_page(
        actor_id=administrator.id,
        state="PENDING",
        page=1,
        page_size=20,
    )
    quota = admin_learning_quota_snapshot(actor_id=administrator.id)

    assert submitted.document_id in {item.document_id for item in documents.items}
    document_item = next(
        item for item in documents.items if item.document_id == submitted.document_id
    )
    assert not hasattr(document_item, "content")
    assert bank.id in {item.bank_id for item in banks.items}
    assert appeals.total_items == 0
    assert quota.site.row_version == 1
    assert quota.overrides == ()
