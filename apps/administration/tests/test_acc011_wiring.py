import pytest

from apps.accounts.public import (
    AccountDeletionDisposition,
    AuthorArticleDecision,
    delete_account,
    set_account_enabled,
    set_author_role,
)
from apps.core.events.models import OutboxEvent
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.operations.public import audit_detail, record_audit_entry, search_audit
from tests.fixtures.accounts import (
    account_exists_for_test,
    bootstrap_test_administrator,
    create_test_account,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _meta():
    return {
        "client_ip": "203.0.113.113",
        "trace_code": new_trace_code(),
        "audit_writer": record_audit_entry,
    }


def test_account_lifecycle_writes_real_audit_and_outbox_in_one_transaction():
    admin = bootstrap_test_administrator()
    target = create_test_account(
        email="audit-lifecycle@kaj.test",
        nickname="AuditLifecycle",
        password="Valid-password-1",
    )
    set_author_role(
        actor_id=admin.id,
        account_id=target.id,
        enabled=True,
        **_meta(),
    )
    set_account_enabled(
        actor_id=admin.id,
        account_id=target.id,
        enabled=False,
        **_meta(),
    )
    set_account_enabled(
        actor_id=admin.id,
        account_id=target.id,
        enabled=True,
        **_meta(),
    )
    disposition = AccountDeletionDisposition(
        disposition_id=new_ulid(),
        account_id=target.id,
        decision=AuthorArticleDecision.NO_ARTICLES,
        article_count=0,
    )
    deletion = delete_account(
        actor_id=admin.id,
        account_id=target.id,
        author_disposition=disposition,
        verify_author_disposition=lambda item: item == disposition,
        **_meta(),
    )

    assert not account_exists_for_test(target.id)
    assert deletion.account_id == target.id
    audits = sorted(
        search_audit(target_id=str(target.id), is_admin=True),
        key=lambda item: item.created_at,
    )
    assert [item.action for item in audits] == [
        "accounts.role.set",
        "accounts.account.status",
        "accounts.account.status",
        "accounts.account.delete",
    ]
    assert list(
        OutboxEvent.objects.order_by("occurred_at").values_list("event_type", flat=True)
    ) == [
        "account.author_role_changed.v1",
        "account.disabled.v1",
        "account.enabled.v1",
        "account.deleted.v1",
    ]
    safe_audit = str(
        [
            (
                detail.summary,
                detail.before_safe,
                detail.after_safe,
            )
            for detail in (
                audit_detail(entry_id=item.id, is_admin=True) for item in audits
            )
        ]
    )
    safe_events = str(list(OutboxEvent.objects.values_list("payload", flat=True)))
    for private_value in ("audit-lifecycle@kaj.test", "AuditLifecycle"):
        assert private_value not in safe_audit
        assert private_value not in safe_events
