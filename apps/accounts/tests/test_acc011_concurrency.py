import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import close_old_connections, connection

from apps.accounts.models import Account, RoleAssignment
from apps.accounts.services.bootstrap import bootstrap_administrator
from apps.accounts.services.lifecycle import set_author_role
from apps.core.events.models import OutboxEvent
from apps.core.observability.trace import new_trace_code

pytestmark = pytest.mark.django_db(transaction=True)


def test_concurrent_author_grants_commit_one_role_audit_and_event():
    assert connection.vendor == "postgresql"
    admin = bootstrap_administrator(
        email="admin@kaj.test",
        initial_password="Strong-Initial-Password-411!",
        production=False,
    )
    target = Account.objects.create_account(
        email="concurrent-author@kaj.test",
        password="Valid-password-1",
    )
    barrier = threading.Barrier(2)
    audits = []

    def grant():
        close_old_connections()
        barrier.wait(timeout=5)
        try:
            return set_author_role(
                actor_id=admin.id,
                account_id=target.id,
                enabled=True,
                client_ip="203.0.113.115",
                trace_code=new_trace_code(),
                audit_writer=lambda **row: audits.append(row),
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: grant(), range(2)))

    assert sorted(item.changed for item in results) == [False, True]
    assert (
        RoleAssignment.objects.filter(
            account=target, role=RoleAssignment.Role.AUTHOR
        ).count()
        == 1
    )
    assert len(audits) == 1
    assert (
        OutboxEvent.objects.filter(
            event_type="account.author_role_changed.v1",
            aggregate_id=str(target.id),
        ).count()
        == 1
    )
