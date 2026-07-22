import pytest

from apps.accounts.public import (
    block_ip,
    ip_block_list,
    security_event_list,
    unblock_ip,
)
from apps.accounts.services.bootstrap import bootstrap_administrator
from apps.operations.public import audit_detail, record_audit_entry, search_audit

pytestmark = pytest.mark.django_db(transaction=True)


def test_ip_block_admin_writes_use_operations_audit_port() -> None:
    admin = bootstrap_administrator(
        email="admin@kaj.test",
        initial_password="Strong-Initial-Password-410!",
        production=False,
    )
    row = block_ip(
        address="198.51.100.99",
        note="cross-owner evidence",
        actor_id=admin.id,
        client_ip="203.0.113.99",
        trace_code="KJ-IP-WIRING",
        audit_writer=record_audit_entry,
    )
    entries = search_audit(
        action="accounts.ip_block.block", target_id=row.id, is_admin=True
    )
    assert len(entries) == 1
    detail = audit_detail(entry_id=entries[0].id, is_admin=True)
    assert detail.before_safe == {"active": False, "note_present": False}
    assert detail.after_safe == {"active": True, "note_present": True}
    assert row.address not in str(detail.after_safe)
    assert "cross-owner evidence" not in str(detail.after_safe)

    unblock_ip(
        block_id=row.id,
        actor_id=admin.id,
        client_ip="203.0.113.99",
        trace_code="KJ-IP-WIRING-REMOVE",
        audit_writer=record_audit_entry,
    )
    assert ip_block_list(is_admin=True) == []
    assert len(search_audit(action="accounts.ip_block.unblock", is_admin=True)) == 1
    assert {
        item.event_type for item in security_event_list(is_admin=True, limit=20)
    } >= {"IP_BLOCK_APPLIED", "IP_BLOCK_REMOVED"}
