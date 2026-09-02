from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.apps import apps
from django.db import IntegrityError, transaction

from apps.core.ids import new_ulid
from apps.learning.contracts import (
    CURRENT_UPLOAD_STATEMENT_VERSION,
    KnowledgeDocumentState,
    KnowledgeReviewRunState,
    LearningModelRunKind,
    LearningModelRunStatus,
)

pytestmark = pytest.mark.django_db(transaction=True)
NOW = datetime(2026, 8, 17, 7, 0, tzinfo=UTC)


def _account(label: str):
    account_model = apps.get_model("accounts", "Account")
    return account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )


def _document(owner, *, state=KnowledgeDocumentState.REVIEW_PENDING, **overrides):
    document_model = apps.get_model("learning", "KnowledgeDocument")
    values = {
        "owner": owner,
        "media_asset_id": new_ulid(),
        "original_name": "schema.md",
        "title": "Schema",
        "summary": "Schema summary",
        "content_sha256": uuid4().hex * 2,
        "character_count": 12,
        "line_count": 2,
        "estimated_tokens": 12,
        "state": state,
        "statement_version": CURRENT_UPLOAD_STATEMENT_VERSION,
        "statement_accepted_by": owner,
        "statement_accepted_at": NOW,
        "submission_idempotency_key": f"schema:{uuid4()}",
    }
    values.update(overrides)
    return document_model.objects.create(**values)


def test_document_content_and_failure_shapes_are_database_enforced() -> None:
    owner = _account("schema-document")

    with pytest.raises(IntegrityError), transaction.atomic():
        _document(owner, title=None)
    with pytest.raises(IntegrityError), transaction.atomic():
        _document(
            owner,
            state=KnowledgeDocumentState.REJECTED,
            failure_purge_after=None,
        )


def test_owner_digest_and_one_active_review_are_database_unique() -> None:
    owner = _account("schema-unique")
    digest = "a" * 64
    first = _document(owner, content_sha256=digest)

    with pytest.raises(IntegrityError), transaction.atomic():
        _document(owner, content_sha256=digest)

    review_model = apps.get_model("learning", "KnowledgeReviewRun")
    first_run = review_model.objects.create(
        document=first,
        sequence=1,
        state=KnowledgeReviewRunState.PENDING,
        input_content_sha256=digest,
        idempotency_key=f"schema-review:{uuid4()}",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        review_model.objects.create(
            document=first,
            sequence=2,
            state=KnowledgeReviewRunState.RUNNING,
            input_content_sha256=digest,
            idempotency_key=f"schema-review:{uuid4()}",
            started_at=NOW,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        review_model.objects.filter(pk=first_run.id).update(
            last_error_code="postgresql://private"
        )


def test_quota_and_reservation_shapes_are_database_enforced() -> None:
    policy_model = apps.get_model("learning", "LearningQuotaPolicy")
    with pytest.raises(IntegrityError), transaction.atomic():
        policy_model.objects.filter(pk=1).update(daily_uploads=0)

    owner = _account("schema-reservation")
    reservation_model = apps.get_model("learning", "LearningModelRunReservation")
    with pytest.raises(IntegrityError), transaction.atomic():
        reservation_model.objects.create(
            account=owner,
            kind=LearningModelRunKind.REVIEW,
            owner_ref=str(uuid4()),
            idempotency_key=f"schema-reservation:{uuid4()}",
            status=LearningModelRunStatus.ACTIVE,
            lease_expires_at=NOW + timedelta(minutes=5),
            released_at=NOW,
        )
