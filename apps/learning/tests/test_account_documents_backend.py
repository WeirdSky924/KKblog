from datetime import timedelta

import pytest
from django.apps import apps
from django.db import transaction

from apps.accounts.models import RoleAssignment
from apps.core.events.models import OutboxEvent
from apps.core.observability.trace import new_trace_code
from apps.learning.public import (
    KnowledgeDocumentAccessPurpose,
    KnowledgeDocumentState,
    KnowledgeReviewOutcome,
    LearningAppealDecision,
    LearningAppealState,
    LearningCommandError,
    complete_knowledge_review,
    owner_document_access_history,
    read_knowledge_document_text,
    retry_document_review,
    review_learning_appeal,
    submit_learning_appeal,
    withdraw_learning_appeal,
)
from apps.media.public import MediaAccessError

from .test_documents_lifecycle import NOW, _account, _claim, _submitted

pytestmark = pytest.mark.django_db(transaction=True)


def _administrator(label: str):
    account = _account(label)
    RoleAssignment.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _rejected(root, owner, *, key: str):
    submitted, asset, storage = _submitted(
        root,
        owner,
        "# Rejected\nKnowledge\n",
        key,
    )
    _claim(submitted)
    complete_knowledge_review(
        document_id=submitted.document_id,
        review_run_id=submitted.review_run_id,
        expected_document_version=2,
        outcome=KnowledgeReviewOutcome.REJECTED,
        safe_reason_code="review_rejected",
        safe_summary="文档未通过审核。",
        risk_categories=("policy",),
        now=NOW + timedelta(minutes=2),
    )
    return submitted, asset, storage


def _approved(
    root,
    owner,
    *,
    key: str,
    content: str = "# Approved\nKnowledge\n",
):
    submitted, asset, storage = _submitted(
        root,
        owner,
        content,
        key,
    )
    _claim(submitted)
    complete_knowledge_review(
        document_id=submitted.document_id,
        review_run_id=submitted.review_run_id,
        expected_document_version=2,
        outcome=KnowledgeReviewOutcome.APPROVED,
        safe_reason_code="knowledge_valid",
        safe_summary="文档通过审核。",
        risk_categories=(),
        now=NOW + timedelta(minutes=2),
    )
    return submitted, asset, storage


def test_appeal_is_single_pending_rendered_safely_and_withdrawable(
    isolated_media_root,
) -> None:
    owner = _account("appeal-owner")
    submitted, _, _ = _rejected(
        isolated_media_root,
        owner,
        key="appeal:single",
    )
    document_model = apps.get_model("learning", "KnowledgeDocument")
    document = document_model.objects.get(pk=submitted.document_id)

    appeal = submit_learning_appeal(
        owner_id=owner.id,
        document_id=document.id,
        expected_document_version=document.row_version,
        reason_markdown="## 申诉理由\n\n<script>alert(1)</script>请重新审核。",
        now=NOW + timedelta(minutes=3),
    )
    assert appeal.state == LearningAppealState.PENDING
    assert "<script>" not in appeal.reason_html
    assert "请重新审核" in appeal.reason_html

    with pytest.raises(LearningCommandError) as duplicate:
        submit_learning_appeal(
            owner_id=owner.id,
            document_id=document.id,
            expected_document_version=document.row_version,
            reason_markdown="再次申诉",
            now=NOW + timedelta(minutes=4),
        )
    assert duplicate.value.code == "learning.appeal_pending.v1"

    withdrawn = withdraw_learning_appeal(
        owner_id=owner.id,
        appeal_id=appeal.appeal_id,
        expected_version=appeal.row_version,
        now=NOW + timedelta(minutes=5),
    )
    assert withdrawn.state == LearningAppealState.WITHDRAWN


@pytest.mark.parametrize(
    ("decision", "expected_state", "event_type"),
    [
        (
            LearningAppealDecision.APPROVED,
            LearningAppealState.APPROVED,
            "learning.appeal_approved.v1",
        ),
        (
            LearningAppealDecision.REJECTED,
            LearningAppealState.REJECTED,
            "learning.appeal_rejected.v1",
        ),
    ],
)
def test_admin_appeal_decision_notifies_and_approval_reenters_review(
    isolated_media_root,
    decision: LearningAppealDecision,
    expected_state: LearningAppealState,
    event_type: str,
) -> None:
    owner = _account(f"appeal-{decision.value.lower()}")
    administrator = _administrator(f"appeal-admin-{decision.value.lower()}")
    submitted, _, _ = _rejected(
        isolated_media_root,
        owner,
        key=f"appeal:{decision.value.lower()}",
    )
    document_model = apps.get_model("learning", "KnowledgeDocument")
    document = document_model.objects.get(pk=submitted.document_id)
    appeal = submit_learning_appeal(
        owner_id=owner.id,
        document_id=document.id,
        expected_document_version=document.row_version,
        reason_markdown="请管理员重新检查审核结果。",
        now=NOW + timedelta(minutes=3),
    )
    dispatches = []

    with transaction.atomic():
        result = review_learning_appeal(
            administrator_id=administrator.id,
            appeal_id=appeal.appeal_id,
            expected_version=appeal.row_version,
            decision=decision,
            decision_markdown="已完成复核。",
            dispatcher=lambda run_id: dispatches.append(run_id),
            trace_code=new_trace_code(),
            client_ip="127.0.0.1",
            now=NOW + timedelta(minutes=4),
        )
        assert dispatches == []
    assert result.state == expected_state
    document.refresh_from_db()
    if decision == LearningAppealDecision.APPROVED:
        assert document.state == KnowledgeDocumentState.REVIEW_PENDING
        assert len(dispatches) == 1
        assert document.review_runs.filter(state="PENDING", sequence=2).exists()
    else:
        assert document.state == KnowledgeDocumentState.REJECTED
        assert dispatches == []
    event = OutboxEvent.objects.get(event_type=event_type)
    assert event.payload == {"recipient_id": str(owner.id)}


def test_owner_retry_rechecks_pending_appeal_and_dispatches_new_review(
    isolated_media_root,
) -> None:
    owner = _account("retry-owner")
    submitted, _, _ = _rejected(
        isolated_media_root,
        owner,
        key="retry:owner",
    )
    document_model = apps.get_model("learning", "KnowledgeDocument")
    document = document_model.objects.get(pk=submitted.document_id)
    appeal = submit_learning_appeal(
        owner_id=owner.id,
        document_id=document.id,
        expected_document_version=document.row_version,
        reason_markdown="先申诉。",
        now=NOW + timedelta(minutes=3),
    )
    with pytest.raises(LearningCommandError) as pending:
        retry_document_review(
            owner_id=owner.id,
            document_id=document.id,
            expected_document_version=document.row_version,
            dispatcher=lambda _run_id: None,
            now=NOW + timedelta(minutes=4),
        )
    assert pending.value.code == "learning.appeal_pending.v1"
    withdraw_learning_appeal(
        owner_id=owner.id,
        appeal_id=appeal.appeal_id,
        expected_version=appeal.row_version,
        now=NOW + timedelta(minutes=5),
    )
    dispatches = []
    retried = retry_document_review(
        owner_id=owner.id,
        document_id=document.id,
        expected_document_version=document.row_version,
        dispatcher=lambda run_id: dispatches.append(run_id),
        now=NOW + timedelta(minutes=6),
    )
    assert retried.document_state == KnowledgeDocumentState.REVIEW_PENDING
    assert len(dispatches) == 1


def test_original_text_access_is_private_and_admin_success_is_audited(
    isolated_media_root,
) -> None:
    owner = _account("access-owner")
    administrator = _administrator("access-admin")
    stranger = _account("access-stranger")
    submitted, _, storage = _approved(
        isolated_media_root,
        owner,
        key="access:approved",
    )

    owned = read_knowledge_document_text(
        actor_id=owner.id,
        document_id=submitted.document_id,
        purpose=KnowledgeDocumentAccessPurpose.OWNER_VIEW,
        trace_code=new_trace_code(),
        storage=storage,
        now=NOW + timedelta(minutes=3),
    )
    assert "# Approved" in owned.content
    access_model = apps.get_model("learning", "KnowledgeDocumentAccess")
    assert access_model.objects.count() == 0

    trace_code = new_trace_code()
    first = read_knowledge_document_text(
        actor_id=administrator.id,
        document_id=submitted.document_id,
        purpose=KnowledgeDocumentAccessPurpose.ADMIN_REVIEW,
        trace_code=trace_code,
        storage=storage,
        now=NOW + timedelta(minutes=4),
    )
    second = read_knowledge_document_text(
        actor_id=administrator.id,
        document_id=submitted.document_id,
        purpose=KnowledgeDocumentAccessPurpose.ADMIN_REVIEW,
        trace_code=trace_code,
        storage=storage,
        now=NOW + timedelta(minutes=4),
    )
    assert first.content == second.content
    assert access_model.objects.count() == 1
    history = owner_document_access_history(
        owner_id=owner.id,
        document_id=submitted.document_id,
        page=1,
        page_size=20,
    )
    assert len(history.items) == 1
    assert history.items[0].purpose == KnowledgeDocumentAccessPurpose.ADMIN_REVIEW
    assert not hasattr(history.items[0], "administrator_id")

    with pytest.raises((LearningCommandError, MediaAccessError)):
        read_knowledge_document_text(
            actor_id=stranger.id,
            document_id=submitted.document_id,
            purpose=KnowledgeDocumentAccessPurpose.OWNER_VIEW,
            trace_code=new_trace_code(),
            storage=storage,
            now=NOW + timedelta(minutes=5),
        )
    assert access_model.objects.count() == 1


def test_administrator_owner_can_use_admin_review_purpose(
    isolated_media_root,
) -> None:
    administrator = _administrator("access-admin-owner")
    submitted, _, storage = _approved(
        isolated_media_root,
        administrator,
        key="access:admin-owner",
    )

    readable = read_knowledge_document_text(
        actor_id=administrator.id,
        document_id=submitted.document_id,
        purpose=KnowledgeDocumentAccessPurpose.ADMIN_REVIEW,
        trace_code=new_trace_code(),
        storage=storage,
        now=NOW + timedelta(minutes=3),
    )

    assert "# Approved" in readable.content
    access_model = apps.get_model("learning", "KnowledgeDocumentAccess")
    assert access_model.objects.filter(
        document_id=submitted.document_id,
        administrator_actor_id=administrator.id,
        purpose=KnowledgeDocumentAccessPurpose.ADMIN_REVIEW,
    ).exists()
