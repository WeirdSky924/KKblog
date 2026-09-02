from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from django.apps import apps
from django.db import connections

from apps.learning.public import (
    CURRENT_UPLOAD_STATEMENT_VERSION,
    DocumentSubmissionOutcome,
    KnowledgeDocumentState,
    KnowledgeReviewRunState,
    LearningCommandError,
    LearningQuotaLimits,
    configure_site_quota_policy,
    owner_knowledge_document,
    submit_knowledge_document,
)
from apps.media.public import MediaAccessError, MediaPurpose, authorize_asset_read
from apps.media.services.uploads import stage_upload
from apps.media.storage import FilesystemMediaStorage

pytestmark = pytest.mark.django_db(transaction=True)
NOW = datetime(2026, 8, 17, 5, 30, tzinfo=UTC)


def _account(label: str, *, author: bool = False, administrator: bool = False):
    account_model = apps.get_model("accounts", "Account")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    role_model = apps.get_model("accounts", "RoleAssignment")
    if author:
        role_model.objects.create(account=account, role="AUTHOR")
        account.attachment_upload_enabled = True
        account.save(update_fields=("attachment_upload_enabled", "updated_at"))
    if administrator:
        role_model.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _stage(root: Path, owner, content: str, *, name: str = "knowledge.md"):
    return stage_upload(
        owner_id=owner.id,
        purpose=MediaPurpose.KNOWLEDGE_DOCUMENT,
        original_name=name,
        declared_content_type="text/markdown",
        chunks=[content.encode("utf-8")],
        storage=FilesystemMediaStorage(root),
        capacity_check=lambda: None,
    )


def _submit(owner, asset, root: Path, *, key: str, now=NOW):
    return submit_knowledge_document(
        owner_id=owner.id,
        asset_id=asset.id,
        statement_version=CURRENT_UPLOAD_STATEMENT_VERSION,
        accepted=True,
        idempotency_key=key,
        dispatcher=lambda _run_id: None,
        storage=FilesystemMediaStorage(root),
        now=now,
    )


@pytest.mark.parametrize(
    ("statement_version", "accepted", "expected_code"),
    [
        (CURRENT_UPLOAD_STATEMENT_VERSION, False, "learning.statement_required.v1"),
        ("knowledge-upload.v0", True, "learning.statement_outdated.v1"),
    ],
)
def test_submission_requires_current_explicit_statement(
    isolated_media_root: Path,
    statement_version: str,
    accepted: bool,
    expected_code: str,
) -> None:
    owner = _account("statement", author=True)
    asset = _stage(isolated_media_root, owner, "# Statement\n")

    with pytest.raises(LearningCommandError) as captured:
        submit_knowledge_document(
            owner_id=owner.id,
            asset_id=asset.id,
            statement_version=statement_version,
            accepted=accepted,
            idempotency_key=f"statement:{uuid4()}",
            dispatcher=lambda _run_id: None,
            storage=FilesystemMediaStorage(isolated_media_root),
            now=NOW,
        )
    assert captured.value.code == expected_code
    assert not apps.get_model("learning", "KnowledgeDocument").objects.exists()
    assert not asset.bindings.exists()


def test_submission_rechecks_attachment_capability_after_upload(
    isolated_media_root: Path,
) -> None:
    owner = _account("capability", author=True)
    asset = _stage(isolated_media_root, owner, "# Capability\n")
    owner.attachment_upload_enabled = False
    owner.save(update_fields=("attachment_upload_enabled", "updated_at"))

    with pytest.raises(LearningCommandError) as captured:
        _submit(owner, asset, isolated_media_root, key="capability:revoked")
    assert captured.value.code == "learning.attachment_capability_required.v1"
    assert not asset.bindings.exists()


def test_submission_normalizes_metadata_binds_media_and_creates_review(
    isolated_media_root: Path,
) -> None:
    owner = _account("submit", author=True)
    administrator = _account("submit-admin", administrator=True)
    stranger = _account("submit-stranger", author=True)
    raw = "\ufeff# 核心标题\r\n\r\n第一段知识。\r第二行。\r\n"
    normalized = "# 核心标题\n\n第一段知识。\n第二行。\n"
    asset = _stage(isolated_media_root, owner, raw, name="safe-name.md")

    result = _submit(owner, asset, isolated_media_root, key="submit:normal")
    document_model = apps.get_model("learning", "KnowledgeDocument")
    run_model = apps.get_model("learning", "KnowledgeReviewRun")
    usage_model = apps.get_model("learning", "LearningDailyUsage")
    document = document_model.objects.get(pk=result.document_id)
    run = run_model.objects.get(pk=result.review_run_id)

    assert result.outcome == DocumentSubmissionOutcome.CREATED
    assert document.state == KnowledgeDocumentState.REVIEW_PENDING
    assert document.media_asset_id == asset.id
    assert document.original_name == "safe-name.md"
    assert document.title == "核心标题"
    assert document.summary == "第一段知识。"
    assert document.content_sha256 == sha256(normalized.encode()).hexdigest()
    assert document.character_count == len(normalized)
    assert document.line_count == 5
    assert document.estimated_tokens == (len(normalized.encode()) + 1) // 2
    assert document.statement_version == CURRENT_UPLOAD_STATEMENT_VERSION
    assert document.statement_accepted_by_id == owner.id
    assert document.statement_accepted_at == NOW
    assert document.row_version == 1
    assert run.state == KnowledgeReviewRunState.PENDING
    assert run.input_content_sha256 == document.content_sha256
    assert run.sequence == 1
    assert asset.bindings.get().slot == "source"
    assert usage_model.objects.get(account=owner).uploads_created == 1

    owner_projection = owner_knowledge_document(
        owner_id=owner.id,
        document_id=document.id,
    )
    assert owner_projection.document_id == document.id
    assert owner_projection.content_sha256 == document.content_sha256
    assert not hasattr(owner_projection, "content")
    assert authorize_asset_read(actor_id=owner.id, asset_id=asset.id)
    assert authorize_asset_read(actor_id=administrator.id, asset_id=asset.id)
    with pytest.raises(MediaAccessError):
        authorize_asset_read(actor_id=stranger.id, asset_id=asset.id)


def test_idempotency_duplicate_scope_and_cross_account_privacy(
    isolated_media_root: Path,
) -> None:
    owner = _account("dedupe-owner", author=True)
    other = _account("dedupe-other", author=True)
    first = _stage(isolated_media_root, owner, "\ufeff# Same\r\nBody\r\n")
    created = _submit(owner, first, isolated_media_root, key="dedupe:first")

    repeated = _submit(owner, first, isolated_media_root, key="dedupe:first")
    assert repeated.document_id == created.document_id
    assert repeated.outcome == DocumentSubmissionOutcome.IDEMPOTENT

    conflicting_asset = _stage(isolated_media_root, owner, "# Different\n")
    with pytest.raises(LearningCommandError) as idempotency_conflict:
        _submit(
            owner,
            conflicting_asset,
            isolated_media_root,
            key="dedupe:first",
        )
    assert idempotency_conflict.value.code == "learning.idempotency_conflict.v1"

    duplicate_asset = _stage(isolated_media_root, owner, "# Same\nBody\n")
    with pytest.raises(LearningCommandError) as duplicate:
        _submit(owner, duplicate_asset, isolated_media_root, key="dedupe:second")
    assert duplicate.value.code == "learning.document_duplicate.v1"
    assert duplicate.value.document_id == created.document_id
    assert not duplicate_asset.bindings.exists()

    other_asset = _stage(isolated_media_root, other, "# Same\nBody\n")
    other_result = _submit(other, other_asset, isolated_media_root, key="dedupe:other")
    assert other_result.document_id != created.document_id

    usage_model = apps.get_model("learning", "LearningDailyUsage")
    assert usage_model.objects.get(account=owner).uploads_created == 1
    assert usage_model.objects.get(account=other).uploads_created == 1


def test_daily_upload_and_pending_review_quotas_are_server_side(
    isolated_media_root: Path,
) -> None:
    administrator = _account("submit-quota-admin", administrator=True)
    configure_site_quota_policy(
        actor_id=administrator.id,
        expected_version=1,
        limits=LearningQuotaLimits(
            daily_uploads=10,
            pending_reviews=1,
            daily_generations=5,
            concurrent_model_runs=1,
            unpurged_banks=100,
        ),
        trace_code="KJ-SUBMIT-PENDING-QUOTA",
        client_ip="127.0.0.1",
    )
    pending_owner = _account("pending-quota", author=True)
    first = _stage(isolated_media_root, pending_owner, "# First\n")
    second = _stage(isolated_media_root, pending_owner, "# Second\n")
    _submit(pending_owner, first, isolated_media_root, key="pending:first")
    with pytest.raises(LearningCommandError) as pending:
        _submit(pending_owner, second, isolated_media_root, key="pending:second")
    assert pending.value.code == "learning.pending_quota_exhausted.v1"

    configure_site_quota_policy(
        actor_id=administrator.id,
        expected_version=2,
        limits=LearningQuotaLimits(
            daily_uploads=1,
            pending_reviews=20,
            daily_generations=5,
            concurrent_model_runs=1,
            unpurged_banks=100,
        ),
        trace_code="KJ-SUBMIT-DAILY-QUOTA",
        client_ip="127.0.0.1",
    )
    daily_owner = _account("daily-quota", author=True)
    daily_first = _stage(isolated_media_root, daily_owner, "# Daily first\n")
    daily_second = _stage(isolated_media_root, daily_owner, "# Daily second\n")
    _submit(daily_owner, daily_first, isolated_media_root, key="daily:first")
    with pytest.raises(LearningCommandError) as daily:
        _submit(daily_owner, daily_second, isolated_media_root, key="daily:second")
    assert daily.value.code == "learning.daily_upload_quota_exhausted.v1"


def test_concurrent_same_owner_digest_creates_one_document(
    isolated_media_root: Path,
) -> None:
    owner = _account("dedupe-concurrent", author=True)
    assets = (
        _stage(isolated_media_root, owner, "\ufeff# Concurrent\r\nBody\r\n"),
        _stage(isolated_media_root, owner, "# Concurrent\nBody\n"),
    )

    def worker(index: int) -> tuple[str, str | None]:
        connections.close_all()
        try:
            result = _submit(
                owner,
                assets[index],
                isolated_media_root,
                key=f"dedupe:concurrent:{index}",
            )
        except LearningCommandError as exc:
            return exc.code, str(exc.document_id) if exc.document_id else None
        finally:
            connections.close_all()
        return "created", str(result.document_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(worker, range(2)))
    assert sorted(item[0] for item in outcomes) == [
        "created",
        "learning.document_duplicate.v1",
    ]
    document_model = apps.get_model("learning", "KnowledgeDocument")
    usage_model = apps.get_model("learning", "LearningDailyUsage")
    assert document_model.objects.filter(owner=owner).count() == 1
    assert usage_model.objects.get(account=owner).uploads_created == 1
    assert sum(asset.bindings.exists() for asset in assets) == 1
