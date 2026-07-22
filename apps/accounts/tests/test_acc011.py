import uuid

import pytest
from django.db import IntegrityError

from apps.accounts.deletion import (
    AccountDeletionDisposition,
    AuthorArticleDecision,
)
from apps.accounts.models import (
    Account,
    AccountDeletion,
    LoginSession,
    RoleAssignment,
)
from apps.accounts.services.authentication import (
    AuthenticationError,
    authenticate_password,
)
from apps.accounts.services.bootstrap import bootstrap_administrator
from apps.accounts.services.lifecycle import (
    AccountLifecycleError,
    delete_account,
    set_account_enabled,
    set_author_role,
)
from apps.core.events.models import OutboxEvent
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def admin():
    return bootstrap_administrator(
        email="admin@kaj.test",
        initial_password="Strong-Initial-Password-411!",
        production=False,
    )


@pytest.fixture
def account():
    return Account.objects.create_account(
        email="lifecycle-user@kaj.test",
        nickname="KajUser",
        password="Valid-password-1",
    )


@pytest.fixture
def audits():
    rows = []

    def writer(**kwargs):
        rows.append(kwargs)

    return rows, writer


def _meta():
    return {
        "client_ip": "203.0.113.111",
        "trace_code": new_trace_code(),
    }


def test_author_role_is_admin_only_idempotent_and_audited(admin, account, audits):
    rows, writer = audits
    granted = set_author_role(
        actor_id=admin.id,
        account_id=account.id,
        enabled=True,
        audit_writer=writer,
        **_meta(),
    )
    assert granted.enabled is True
    assert granted.changed is True
    assert RoleAssignment.objects.filter(
        account=account, role=RoleAssignment.Role.AUTHOR
    ).exists()
    assert rows[-1]["action"] == "accounts.role.set"
    assert rows[-1]["before"]["roles"] == []
    assert rows[-1]["after"]["roles"] == ["AUTHOR"]
    event = OutboxEvent.objects.get(event_type="account.author_role_changed.v1")
    assert event.aggregate_id == str(account.id)
    assert event.payload == {"enabled": True}
    assert account.email not in str(event.payload)

    unchanged = set_author_role(
        actor_id=admin.id,
        account_id=account.id,
        enabled=True,
        audit_writer=writer,
        **_meta(),
    )
    assert unchanged.changed is False
    assert len(rows) == 1
    assert OutboxEvent.objects.count() == 1

    revoked = set_author_role(
        actor_id=admin.id,
        account_id=account.id,
        enabled=False,
        audit_writer=writer,
        **_meta(),
    )
    assert revoked.enabled is False
    assert not RoleAssignment.objects.filter(
        account=account, role=RoleAssignment.Role.AUTHOR
    ).exists()
    account.refresh_from_db()
    assert account.id == revoked.account_id
    assert (
        OutboxEvent.objects.filter(event_type="account.author_role_changed.v1").count()
        == 2
    )

    with pytest.raises(AccountLifecycleError, match="管理员作者角色"):
        set_author_role(
            actor_id=admin.id,
            account_id=admin.id,
            enabled=False,
            audit_writer=writer,
            **_meta(),
        )


def test_database_and_service_preserve_the_unique_administrator(admin, account, audits):
    _, writer = audits
    with pytest.raises(IntegrityError):
        RoleAssignment.objects.create(
            account=account,
            role=RoleAssignment.Role.ADMINISTRATOR,
            granted_by=admin,
        )
    with pytest.raises(AccountLifecycleError, match="管理员账户"):
        set_account_enabled(
            actor_id=admin.id,
            account_id=admin.id,
            enabled=False,
            audit_writer=writer,
            **_meta(),
        )


def test_disable_revokes_sessions_enable_does_not_restore_them(admin, account, audits):
    rows, writer = audits
    _, first = LoginSession.issue(account=account, remember=False)
    _, second = LoginSession.issue(account=account, remember=True)

    disabled = set_account_enabled(
        actor_id=admin.id,
        account_id=account.id,
        enabled=False,
        audit_writer=writer,
        **_meta(),
    )
    account.refresh_from_db()
    first.refresh_from_db()
    second.refresh_from_db()
    assert account.status == Account.Status.DISABLED
    assert disabled.revoked_sessions == 2
    assert first.revoked_at is not None and second.revoked_at is not None
    assert OutboxEvent.objects.get().event_type == "account.disabled.v1"
    with pytest.raises(AuthenticationError, match="不可登录"):
        authenticate_password(
            email=account.email,
            password="Valid-password-1",
            remember=False,
            client_ip="203.0.113.111",
            trace_code=new_trace_code(),
        )

    repeated = set_account_enabled(
        actor_id=admin.id,
        account_id=account.id,
        enabled=False,
        audit_writer=writer,
        **_meta(),
    )
    assert repeated.changed is False
    assert len(rows) == 1

    enabled = set_account_enabled(
        actor_id=admin.id,
        account_id=account.id,
        enabled=True,
        audit_writer=writer,
        **_meta(),
    )
    account.refresh_from_db()
    assert account.status == Account.Status.ACTIVE
    assert enabled.revoked_sessions == 0
    recovered = authenticate_password(
        email=account.email,
        password="Valid-password-1",
        remember=False,
        client_ip="203.0.113.111",
        trace_code=new_trace_code(),
    )
    assert recovered.account.id == account.id
    assert (
        LoginSession.objects.filter(account=account, revoked_at__isnull=True).count()
        == 1
    )
    assert list(
        OutboxEvent.objects.order_by("occurred_at").values_list("event_type", flat=True)
    ) == ["account.disabled.v1", "account.enabled.v1"]
    assert [row["action"] for row in rows] == [
        "accounts.account.status",
        "accounts.account.status",
    ]


def test_non_author_delete_releases_identity_and_never_reuses_uuid(
    admin, account, audits
):
    rows, writer = audits
    old_id = account.id
    disposition = AccountDeletionDisposition(
        disposition_id=new_ulid(),
        account_id=account.id,
        decision=AuthorArticleDecision.NO_ARTICLES,
        article_count=0,
    )
    deletion = delete_account(
        actor_id=admin.id,
        account_id=account.id,
        author_disposition=disposition,
        verify_author_disposition=lambda item: item == disposition,
        audit_writer=writer,
        **_meta(),
    )
    assert deletion.account_id == old_id
    assert deletion.was_author is False
    assert not Account.objects.filter(pk=old_id).exists()
    assert not LoginSession.objects.filter(account_id=old_id).exists()
    assert AccountDeletion.objects.filter(pk=deletion.id).exists()
    event = OutboxEvent.objects.get(event_type="account.deleted.v1")
    assert event.aggregate_id == str(old_id)
    assert event.payload["deletion_id"] == deletion.id
    assert "lifecycle-user@kaj.test" not in str(event.payload)
    assert "KajUser" not in str(event.payload)
    assert rows[-1]["action"] == "accounts.account.delete"

    replacement = Account.objects.create_account(
        email="lifecycle-user@kaj.test",
        nickname="kajuser",
        password="Another-password-2",
    )
    assert replacement.id != old_id


def test_author_delete_requires_matching_content_owned_disposition(
    admin, account, audits
):
    _, writer = audits
    set_author_role(
        actor_id=admin.id,
        account_id=account.id,
        enabled=True,
        audit_writer=writer,
        **_meta(),
    )
    with pytest.raises(AccountLifecycleError, match="文章处置"):
        delete_account(
            actor_id=admin.id,
            account_id=account.id,
            author_disposition=None,
            verify_author_disposition=None,
            audit_writer=writer,
            **_meta(),
        )

    disposition = AccountDeletionDisposition(
        disposition_id=new_ulid(),
        account_id=account.id,
        decision=AuthorArticleDecision.DELETE_ALL,
        article_count=2,
    )
    with pytest.raises(AccountLifecycleError, match="文章处置"):
        delete_account(
            actor_id=admin.id,
            account_id=account.id,
            author_disposition=disposition,
            verify_author_disposition=lambda item: False,
            audit_writer=writer,
            **_meta(),
        )
    assert Account.objects.filter(pk=account.id).exists()

    deletion = delete_account(
        actor_id=admin.id,
        account_id=account.id,
        author_disposition=disposition,
        verify_author_disposition=lambda item: item == disposition,
        audit_writer=writer,
        **_meta(),
    )
    assert deletion.was_author is True
    assert deletion.author_disposition == AuthorArticleDecision.DELETE_ALL
    assert deletion.disposition_id == disposition.disposition_id


def test_former_author_cannot_bypass_article_disposition(admin, audits):
    _, writer = audits
    former_author = Account.objects.create_account(
        email="former-author@kaj.test",
        password="Valid-password-1",
    )
    for enabled in (True, False):
        set_author_role(
            actor_id=admin.id,
            account_id=former_author.id,
            enabled=enabled,
            audit_writer=writer,
            **_meta(),
        )
    with pytest.raises(AccountLifecycleError, match="文章处置"):
        delete_account(
            actor_id=admin.id,
            account_id=former_author.id,
            author_disposition=None,
            verify_author_disposition=None,
            audit_writer=writer,
            **_meta(),
        )
    assert Account.objects.filter(pk=former_author.id).exists()


def test_lifecycle_rolls_back_when_audit_port_fails(admin, account):
    def reject(**kwargs):
        del kwargs
        raise RuntimeError("audit unavailable")

    with pytest.raises(RuntimeError, match="audit unavailable"):
        set_author_role(
            actor_id=admin.id,
            account_id=account.id,
            enabled=True,
            audit_writer=reject,
            **_meta(),
        )
    assert not RoleAssignment.objects.filter(
        account=account, role=RoleAssignment.Role.AUTHOR
    ).exists()
    assert OutboxEvent.objects.count() == 0

    unknown_id = uuid.uuid4()
    with pytest.raises(AccountLifecycleError, match="不存在"):
        set_account_enabled(
            actor_id=admin.id,
            account_id=unknown_id,
            enabled=False,
            audit_writer=reject,
            **_meta(),
        )
