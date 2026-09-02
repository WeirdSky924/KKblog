from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from django.apps import apps

from apps.learning.public import (
    CURRENT_UPLOAD_STATEMENT_VERSION,
    KnowledgeDocumentState,
    KnowledgeReviewOutcome,
    KnowledgeReviewRunState,
    LearningCleanupOutcome,
    LearningCommandError,
    claim_knowledge_review,
    complete_knowledge_review,
    delete_knowledge_document,
    purge_due_knowledge_document,
    purge_failed_knowledge_document,
    restore_knowledge_document,
    submit_knowledge_document,
)
from apps.media.public import MediaAccessError, MediaPurpose, authorize_asset_read
from apps.media.services.uploads import stage_upload
from apps.media.storage import FilesystemMediaStorage

pytestmark = pytest.mark.django_db(transaction=True)
NOW = datetime(2026, 8, 17, 6, 0, tzinfo=UTC)


def _account(label: str):
    account_model = apps.get_model("accounts", "Account")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    role_model = apps.get_model("accounts", "RoleAssignment")
    role_model.objects.create(account=account, role="AUTHOR")
    account.attachment_upload_enabled = True
    account.save(update_fields=("attachment_upload_enabled", "updated_at"))
    return account


def _submitted(root: Path, owner, content: str, key: str):
    storage = FilesystemMediaStorage(root)
    asset = stage_upload(
        owner_id=owner.id,
        purpose=MediaPurpose.KNOWLEDGE_DOCUMENT,
        original_name="lifecycle.md",
        declared_content_type="text/markdown",
        chunks=[content.encode()],
        storage=storage,
        capacity_check=lambda: None,
    )
    result = submit_knowledge_document(
        owner_id=owner.id,
        asset_id=asset.id,
        statement_version=CURRENT_UPLOAD_STATEMENT_VERSION,
        accepted=True,
        idempotency_key=key,
        dispatcher=lambda _run_id: None,
        storage=storage,
        now=NOW,
    )
    return result, asset, storage


def _claim(result):
    return claim_knowledge_review(
        document_id=result.document_id,
        review_run_id=result.review_run_id,
        expected_document_version=1,
        now=NOW + timedelta(minutes=1),
    )


def test_review_claim_and_approved_outcome_follow_single_state_machine(
    isolated_media_root: Path,
) -> None:
    owner = _account("review-approved")
    result, _, _ = _submitted(
        isolated_media_root,
        owner,
        "# Approved\nKnowledge\n",
        "review:approved",
    )
    claimed = _claim(result)
    assert claimed.document_state == KnowledgeDocumentState.REVIEWING
    assert claimed.run_state == KnowledgeReviewRunState.RUNNING

    completed = complete_knowledge_review(
        document_id=result.document_id,
        review_run_id=result.review_run_id,
        expected_document_version=2,
        outcome=KnowledgeReviewOutcome.APPROVED,
        safe_reason_code="knowledge_valid",
        safe_summary="文档已通过审核。",
        risk_categories=("none",),
        now=NOW + timedelta(minutes=2),
    )
    document_model = apps.get_model("learning", "KnowledgeDocument")
    run_model = apps.get_model("learning", "KnowledgeReviewRun")
    document = document_model.objects.get(pk=result.document_id)
    run = run_model.objects.get(pk=result.review_run_id)
    assert completed.document_state == KnowledgeDocumentState.APPROVED
    assert document.state == KnowledgeDocumentState.APPROVED
    assert document.failure_purge_after is None
    assert document.last_reason_code == "knowledge_valid"
    assert run.state == KnowledgeReviewRunState.APPROVED
    assert run.completed_at == NOW + timedelta(minutes=2)

    with pytest.raises(LearningCommandError) as repeated:
        complete_knowledge_review(
            document_id=result.document_id,
            review_run_id=result.review_run_id,
            expected_document_version=3,
            outcome=KnowledgeReviewOutcome.APPROVED,
            safe_reason_code="knowledge_valid",
            safe_summary="重复完成。",
            risk_categories=(),
            now=NOW + timedelta(minutes=3),
        )
    assert repeated.value.code == "learning.review_conflict.v1"


@pytest.mark.parametrize(
    ("outcome", "expected_document_state", "expected_run_state"),
    [
        (
            KnowledgeReviewOutcome.REJECTED,
            KnowledgeDocumentState.REJECTED,
            KnowledgeReviewRunState.REJECTED,
        ),
        (
            KnowledgeReviewOutcome.FAILED,
            KnowledgeDocumentState.REVIEW_FAILED,
            KnowledgeReviewRunState.FAILED,
        ),
    ],
)
def test_failed_material_retains_thirty_days_then_becomes_tombstone(
    isolated_media_root: Path,
    outcome: KnowledgeReviewOutcome,
    expected_document_state: KnowledgeDocumentState,
    expected_run_state: KnowledgeReviewRunState,
) -> None:
    owner = _account(f"review-{outcome.value.lower()}")
    result, asset, storage = _submitted(
        isolated_media_root,
        owner,
        f"# {outcome.value}\nKnowledge\n",
        f"review:{outcome.value.lower()}",
    )
    _claim(result)
    completed_at = NOW + timedelta(minutes=2)
    complete_knowledge_review(
        document_id=result.document_id,
        review_run_id=result.review_run_id,
        expected_document_version=2,
        outcome=outcome,
        safe_reason_code="review_terminal_reason",
        safe_summary="可安全展示的审核结果。",
        risk_categories=("policy",),
        now=completed_at,
    )
    document_model = apps.get_model("learning", "KnowledgeDocument")
    run_model = apps.get_model("learning", "KnowledgeReviewRun")
    document = document_model.objects.get(pk=result.document_id)
    assert document.state == expected_document_state
    assert document.failure_purge_after == completed_at + timedelta(days=30)
    assert run_model.objects.get(pk=result.review_run_id).state == expected_run_state

    not_due = purge_failed_knowledge_document(
        document_id=document.id,
        now=completed_at + timedelta(days=29),
        storage=storage,
    )
    assert not_due.outcome == LearningCleanupOutcome.NOT_DUE

    purged = purge_failed_knowledge_document(
        document_id=document.id,
        now=completed_at + timedelta(days=30),
        storage=storage,
    )
    document.refresh_from_db()
    run = run_model.objects.get(pk=result.review_run_id)
    assert purged.outcome == LearningCleanupOutcome.CONTENT_PURGED
    assert document.state == KnowledgeDocumentState.CONTENT_PURGED
    assert document.media_asset_id is None
    assert document.content_sha256 is None
    assert document.original_name is None
    assert document.title is None and document.summary is None
    assert document.last_reason_code == "review_terminal_reason"
    assert run.safe_summary is None and run.risk_categories == []
    assert not storage.exists(asset.storage_key)

    replacement, _, _ = _submitted(
        isolated_media_root,
        owner,
        f"# {outcome.value}\nKnowledge\n",
        f"review:{outcome.value.lower()}:replacement",
    )
    assert replacement.document_id != result.document_id


def test_delete_restore_and_final_purge_preserve_cooling_period(
    isolated_media_root: Path,
) -> None:
    owner = _account("document-delete")
    result, asset, storage = _submitted(
        isolated_media_root,
        owner,
        "# Delete\nKnowledge\n",
        "delete:document",
    )
    deletion = delete_knowledge_document(
        owner_id=owner.id,
        document_id=result.document_id,
        expected_version=1,
        now=NOW + timedelta(minutes=1),
    )
    document_model = apps.get_model("learning", "KnowledgeDocument")
    run_model = apps.get_model("learning", "KnowledgeReviewRun")
    document = document_model.objects.get(pk=result.document_id)
    assert deletion.state == KnowledgeDocumentState.DELETE_PENDING
    assert document.pre_delete_state == KnowledgeDocumentState.REVIEW_PENDING
    assert document.purge_after == NOW + timedelta(days=7, minutes=1)
    assert run_model.objects.get(pk=result.review_run_id).state == "CANCELLED"
    with pytest.raises(MediaAccessError):
        authorize_asset_read(actor_id=owner.id, asset_id=asset.id)

    restored = restore_knowledge_document(
        owner_id=owner.id,
        document_id=document.id,
        expected_version=2,
        now=NOW + timedelta(days=1),
    )
    assert restored.state == KnowledgeDocumentState.REVIEW_PENDING

    delete_knowledge_document(
        owner_id=owner.id,
        document_id=document.id,
        expected_version=3,
        now=NOW + timedelta(days=1, minutes=1),
    )
    not_due = purge_due_knowledge_document(
        document_id=document.id,
        now=NOW + timedelta(days=8),
        storage=storage,
    )
    assert not_due.outcome == LearningCleanupOutcome.NOT_DUE
    purged = purge_due_knowledge_document(
        document_id=document.id,
        now=NOW + timedelta(days=8, minutes=1),
        storage=storage,
    )
    document.refresh_from_db()
    assert purged.outcome == LearningCleanupOutcome.DELETED
    assert document.state == KnowledgeDocumentState.DELETED
    assert document.media_asset_id is None and document.content_sha256 is None
    assert document.deleted_at == NOW + timedelta(days=8, minutes=1)
    run = run_model.objects.get(pk=result.review_run_id)
    assert run.input_content_sha256 is None
    assert run.safe_summary is None and run.risk_categories == []
    assert not storage.exists(asset.storage_key)

    with pytest.raises(LearningCommandError) as expired_restore:
        restore_knowledge_document(
            owner_id=owner.id,
            document_id=document.id,
            expected_version=document.row_version,
            now=NOW + timedelta(days=8, minutes=2),
        )
    assert expired_restore.value.code == "learning.document_restore_expired.v1"


def test_delete_during_review_prevents_late_outcome(
    isolated_media_root: Path,
) -> None:
    owner = _account("delete-race")
    result, _, _ = _submitted(
        isolated_media_root,
        owner,
        "# Race\nKnowledge\n",
        "delete:race",
    )
    _claim(result)
    delete_knowledge_document(
        owner_id=owner.id,
        document_id=result.document_id,
        expected_version=2,
        now=NOW + timedelta(minutes=2),
    )

    with pytest.raises(LearningCommandError) as late:
        complete_knowledge_review(
            document_id=result.document_id,
            review_run_id=result.review_run_id,
            expected_document_version=3,
            outcome=KnowledgeReviewOutcome.APPROVED,
            safe_reason_code="late_success",
            safe_summary="不应覆盖删除状态。",
            risk_categories=(),
            now=NOW + timedelta(minutes=3),
        )
    assert late.value.code == "learning.review_conflict.v1"


def test_review_claim_rechecks_attachment_capability(
    isolated_media_root: Path,
) -> None:
    owner = _account("claim-capability")
    result, _, _ = _submitted(
        isolated_media_root,
        owner,
        "# Capability\nKnowledge\n",
        "claim:capability",
    )
    owner.attachment_upload_enabled = False
    owner.save(update_fields=("attachment_upload_enabled", "updated_at"))

    with pytest.raises(LearningCommandError) as captured:
        _claim(result)
    assert captured.value.code == "learning.attachment_capability_required.v1"
