import uuid

import pytest
from django.db import transaction
from django.utils import timezone

from apps.core.ids import new_ulid
from apps.operations.models import AuditEntry, TaskRun
from apps.operations.queries.audit import audit_detail, search_audit
from apps.operations.services.audit import (
    AuditRejected,
    AuditSchema,
    record_audit_entry,
    register_audit_schema,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def business_run() -> TaskRun:
    now = timezone.now()
    return TaskRun.objects.create(
        run_id=new_ulid(),
        task_name="audit.fixture",
        business_object="before",
        idempotency_key=new_ulid(),
        celery_id=str(uuid.uuid4()),
        trace_code="KJ-AUDIT-FIXTURE",
        scheduled_at=now,
        available_at=now,
    )


@pytest.fixture(autouse=True)
def audit_schema() -> None:
    register_audit_schema(
        AuditSchema(
            action="test.account.changed",
            target_type="account",
            allowed_fields=frozenset({"status", "role_ids", "revision_id"}),
        ),
        replace=True,
    )


def test_unknown_or_secret_fields_are_rejected() -> None:
    base = {
        "action": "test.account.changed",
        "actor_id": uuid.uuid4(),
        "target_id": str(uuid.uuid4()),
        "trace_code": "KJ-TEST-AUDIT",
        "client_ip": "203.0.113.9",
    }
    with pytest.raises(AuditRejected):
        record_audit_entry(**base, before={"password": "secret"}, after={})
    with pytest.raises(AuditRejected):
        record_audit_entry(**base, before={"unknown": "value"}, after={})
    assert AuditEntry.objects.count() == 0


def test_audit_failure_rolls_back_enclosing_business_transaction(
    business_run,
) -> None:
    with pytest.raises(AuditRejected), transaction.atomic():
        business_run.business_object = "after"
        business_run.save(update_fields=["business_object", "updated_at"])
        record_audit_entry(
            action="test.account.changed",
            actor_id=uuid.uuid4(),
            target_id=business_run.run_id,
            trace_code="KJ-TEST-ROLLBACK",
            client_ip="2001:db8::8",
            before={"status": "ACTIVE"},
            after={"token": "must-not-write"},
        )
    business_run.refresh_from_db()
    assert business_run.business_object == "before"


def test_query_masks_list_ip_and_reveals_detail_to_admin() -> None:
    target_id = str(uuid.uuid4())
    entry = record_audit_entry(
        action="test.account.changed",
        actor_id=uuid.uuid4(),
        target_id=target_id,
        trace_code="KJ-TEST-QUERY",
        client_ip="203.0.113.77",
        before={"status": "ACTIVE", "revision_id": "01SAFE"},
        after={"status": "DISABLED", "role_ids": ["AUTHOR"]},
        summary="account status changed",
    )
    entry_date = timezone.localdate(entry.created_at)
    rows = search_audit(
        keyword="status",
        action="test.account.changed",
        target_id=target_id,
        start=entry_date,
        end=entry_date,
        is_admin=True,
    )
    assert rows[0].client_ip == "203.0.113.***"
    detail = audit_detail(entry_id=entry.id, is_admin=True)
    assert detail.client_ip == "203.0.113.77"
    assert "password" not in str(detail.before_safe).casefold()


def test_non_admin_cannot_query_audit() -> None:
    with pytest.raises(PermissionError):
        search_audit(is_admin=False)
