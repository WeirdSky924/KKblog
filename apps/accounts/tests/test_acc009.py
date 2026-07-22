from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.test import override_settings

from apps.accounts.models import Account, SecurityEvent
from apps.accounts.queries.security_events import (
    security_event_detail,
    security_event_list,
)
from apps.accounts.services.authentication import (
    AuthenticationError,
    authenticate_code,
    authenticate_password,
    request_login_code,
)
from apps.accounts.services.bootstrap import bootstrap_administrator
from apps.accounts.services.credentials import (
    CredentialError,
    request_password_reset_code,
    reset_password,
)
from apps.accounts.services.restrictions import (
    RestrictionError,
    RestrictionStore,
    clear_account_restrictions,
    clear_ip_send_restriction,
)
from apps.accounts.services.verification import VerificationStore
from apps.core.time.clock import FrozenClock

pytestmark = pytest.mark.django_db(transaction=True)
SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE = datetime(2026, 7, 21, 12, tzinfo=SHANGHAI)


@pytest.fixture
def stores(isolated_redis):
    client, prefix = isolated_redis
    namespace = prefix.rstrip(":")
    restrictions = RestrictionStore(client=client, namespace=namespace)
    verification = VerificationStore(
        client=client,
        namespace=namespace,
        restriction_store=restrictions,
    )
    return restrictions, verification


@pytest.fixture
def account():
    return Account.objects.create_account(
        email="restricted@kaj.test", password="Valid-password-1!"
    )


def test_fifth_password_failure_blocks_password_code_and_reset_for_one_hour(
    account, stores, mailpit
) -> None:
    restrictions, verification = stores
    clock = FrozenClock(BASE.astimezone(UTC))
    request_login_code(
        email=account.email,
        client_ip="203.0.113.51",
        trace_code="KJ-RESTRICT-CODE",
        store=verification,
        restriction_store=restrictions,
        clock=clock,
        code_generator=lambda: "123456",
    )
    with pytest.raises(AuthenticationError, match="验证码无效"):
        authenticate_code(
            email=account.email,
            code="000000",
            remember=False,
            client_ip="203.0.113.51",
            trace_code="KJ-RESTRICT-CODE-WRONG",
            store=verification,
            restriction_store=restrictions,
            clock=clock,
        )
    for attempt in range(1, 5):
        with pytest.raises(AuthenticationError, match="邮箱或密码不正确"):
            authenticate_password(
                email=account.email,
                password="wrong-password",
                remember=False,
                client_ip="203.0.113.51",
                trace_code=f"KJ-RESTRICT-{attempt}",
                restriction_store=restrictions,
                clock=clock,
            )

    with pytest.raises(AuthenticationError, match="该账号暂时限制登录"):
        authenticate_password(
            email=account.email,
            password="wrong-password",
            remember=False,
            client_ip="203.0.113.51",
            trace_code="KJ-RESTRICT-5",
            restriction_store=restrictions,
            clock=clock,
        )
    assert restrictions.is_login_restricted(account_id=account.id, clock=clock)

    with pytest.raises(AuthenticationError, match="该账号暂时限制登录"):
        authenticate_code(
            email=account.email,
            code="123456",
            remember=False,
            client_ip="203.0.113.51",
            trace_code="KJ-RESTRICT-CODE-BLOCK",
            store=verification,
            restriction_store=restrictions,
            clock=clock,
        )
    with pytest.raises(AuthenticationError, match="该账号暂时限制登录"):
        request_login_code(
            email=account.email,
            client_ip="203.0.113.51",
            trace_code="KJ-RESTRICT-CODE-REQUEST",
            store=verification,
            restriction_store=restrictions,
            clock=clock,
        )
    with pytest.raises(CredentialError, match="该账号暂时限制登录"):
        request_password_reset_code(
            email=account.email,
            client_ip="203.0.113.51",
            trace_code="KJ-RESTRICT-RESET",
            store=verification,
            restriction_store=restrictions,
            clock=clock,
        )
    with pytest.raises(CredentialError, match="该账号暂时限制登录"):
        reset_password(
            email=account.email,
            code="123456",
            new_password="Replacement-password-1!",
            client_ip="203.0.113.51",
            trace_code="KJ-RESTRICT-RESET-SUBMIT",
            store=verification,
            restriction_store=restrictions,
            clock=clock,
        )

    result = authenticate_password(
        email=account.email,
        password="Valid-password-1!",
        remember=False,
        client_ip="203.0.113.51",
        trace_code="KJ-RESTRICT-EXPIRED",
        restriction_store=restrictions,
        clock=FrozenClock((BASE + timedelta(hours=1)).astimezone(UTC)),
    )
    assert result.account.id == account.id
    assert (
        SecurityEvent.objects.filter(
            account=account, event_type="LOGIN_RESTRICTION_APPLIED"
        ).count()
        == 1
    )


def test_daily_email_and_ip_limits_reset_at_shanghai_midnight(stores, mailpit) -> None:
    restrictions, verification = stores
    before_midnight = FrozenClock(
        datetime(2026, 7, 21, 23, 59, tzinfo=SHANGHAI).astimezone(UTC)
    )
    for suffix in range(20):
        restrictions.reserve_verification_send(
            email="email-limit@kaj.test",
            client_ip=f"203.0.113.{suffix + 1}",
            clock=before_midnight,
        )
    with pytest.raises(RestrictionError, match="验证码请求过于频繁"):
        restrictions.reserve_verification_send(
            email="email-limit@kaj.test",
            client_ip="203.0.113.30",
            clock=before_midnight,
        )
    for suffix in range(20):
        restrictions.reserve_verification_send(
            email=f"ip-limit-{suffix}@kaj.test",
            client_ip="2001:db8::52",
            clock=before_midnight,
        )
    with pytest.raises(RestrictionError, match="验证码请求过于频繁"):
        restrictions.reserve_verification_send(
            email="ip-limit-final@kaj.test",
            client_ip="2001:db8::52",
            clock=before_midnight,
        )
    with pytest.raises(AuthenticationError, match="验证码请求过于频繁"):
        request_login_code(
            email="email-limit@kaj.test",
            client_ip="203.0.113.31",
            trace_code="KJ-DAILY-LIMIT",
            store=verification,
            restriction_store=restrictions,
            clock=before_midnight,
            code_generator=lambda: "345678",
        )
    assert mailpit.messages() == []
    assert SecurityEvent.objects.filter(
        event_type="VERIFICATION_SEND_RESTRICTED",
        client_ip="203.0.113.31",
    ).exists()

    after_midnight = FrozenClock(
        datetime(2026, 7, 22, 0, 0, tzinfo=SHANGHAI).astimezone(UTC)
    )
    restrictions.reserve_verification_send(
        email="email-limit@kaj.test",
        client_ip="2001:db8::52",
        clock=after_midnight,
    )
    keys = [
        item.decode()
        for item in restrictions.client.scan_iter(match=f"{restrictions.namespace}:*")
    ]
    assert all("@kaj.test" not in key and "2001:db8" not in key for key in keys)


def test_failed_resend_rolls_back_daily_reservation(stores, mailpit) -> None:
    restrictions, verification = stores
    kwargs = {
        "email": "rollback@kaj.test",
        "client_ip": "203.0.113.53",
        "trace_code": "KJ-SEND-ROLLBACK",
        "store": verification,
        "restriction_store": restrictions,
        "clock": FrozenClock(BASE.astimezone(UTC)),
        "code_generator": lambda: "234567",
    }
    request_login_code(**kwargs)
    with pytest.raises(AuthenticationError, match="稍后"):
        request_login_code(**kwargs)

    assert restrictions.verification_send_counts(
        email="rollback@kaj.test",
        client_ip="203.0.113.53",
        clock=kwargs["clock"],
    ) == (1, 1)


def test_redis_flush_safely_clears_temporary_restrictions(account, stores) -> None:
    restrictions, _ = stores
    clock = FrozenClock(BASE.astimezone(UTC))
    for _ in range(5):
        restrictions.record_password_failure(
            email=account.email, account_id=account.id, clock=clock
        )
    keys = list(restrictions.client.scan_iter(match=f"{restrictions.namespace}:*"))
    restrictions.client.delete(*keys)

    result = authenticate_password(
        email=account.email,
        password="Valid-password-1!",
        remember=False,
        client_ip="203.0.113.54",
        trace_code="KJ-REDIS-FLUSH",
        restriction_store=restrictions,
        clock=clock,
    )
    assert result.account.id == account.id


def test_successful_password_breaks_the_consecutive_failure_sequence(
    account, stores
) -> None:
    restrictions, _ = stores
    clock = FrozenClock(BASE.astimezone(UTC))
    for attempt in range(4):
        with pytest.raises(AuthenticationError, match="邮箱或密码不正确"):
            authenticate_password(
                email=account.email,
                password="wrong-password",
                remember=False,
                client_ip="203.0.113.58",
                trace_code=f"KJ-SEQUENCE-A-{attempt}",
                restriction_store=restrictions,
                clock=clock,
            )
    authenticate_password(
        email=account.email,
        password="Valid-password-1!",
        remember=False,
        client_ip="203.0.113.58",
        trace_code="KJ-SEQUENCE-SUCCESS",
        restriction_store=restrictions,
        clock=clock,
    )
    for attempt in range(4):
        with pytest.raises(AuthenticationError, match="邮箱或密码不正确"):
            authenticate_password(
                email=account.email,
                password="wrong-password",
                remember=False,
                client_ip="203.0.113.58",
                trace_code=f"KJ-SEQUENCE-B-{attempt}",
                restriction_store=restrictions,
                clock=clock,
            )
    assert not restrictions.is_login_restricted(account_id=account.id, clock=clock)


def test_admin_clear_is_precise_audited_and_restores_on_audit_failure(
    account, stores
) -> None:
    restrictions, _ = stores
    clock = FrozenClock(BASE.astimezone(UTC))
    admin = bootstrap_administrator(
        email="admin@kaj.test",
        initial_password="Temporary-admin-1!",
        production=False,
    )
    for _ in range(5):
        restrictions.record_password_failure(
            email=account.email, account_id=account.id, clock=clock
        )
    restrictions.reserve_verification_send(
        email=account.email, client_ip="203.0.113.55", clock=clock
    )
    audit_rows = []

    def audit_ok(**kwargs):
        audit_rows.append(kwargs)

    with pytest.raises(RuntimeError, match="audit unavailable"):
        clear_account_restrictions(
            actor_id=admin.id,
            target_account_id=account.id,
            client_ip="203.0.113.56",
            trace_code="KJ-CLEAR-ROLLBACK",
            store=restrictions,
            audit_writer=lambda **kwargs: (_ for _ in ()).throw(
                RuntimeError("audit unavailable")
            ),
            clock=clock,
        )
    assert restrictions.is_login_restricted(account_id=account.id, clock=clock)

    assert (
        clear_account_restrictions(
            actor_id=admin.id,
            target_account_id=account.id,
            client_ip="203.0.113.56",
            trace_code="KJ-CLEAR-ACCOUNT",
            store=restrictions,
            audit_writer=audit_ok,
            clock=clock,
        )
        >= 1
    )
    assert not restrictions.is_login_restricted(account_id=account.id, clock=clock)
    assert (
        clear_ip_send_restriction(
            actor_id=admin.id,
            target_ip="203.0.113.55",
            client_ip="203.0.113.56",
            trace_code="KJ-CLEAR-IP",
            store=restrictions,
            audit_writer=audit_ok,
            clock=clock,
        )
        == 1
    )
    assert [row["action"] for row in audit_rows] == [
        "accounts.restriction.clear",
        "accounts.restriction.clear",
    ]
    assert all(row["target_id"] != "203.0.113.55" for row in audit_rows)


def test_direct_login_post_and_security_event_query_enforce_boundaries(
    client, account, stores
) -> None:
    restrictions, _ = stores
    namespace = restrictions.namespace
    with override_settings(ACCOUNT_RESTRICTION_NAMESPACE=namespace):
        for _ in range(5):
            response = client.post(
                "/accounts/login/",
                {
                    "action": "password",
                    "email": account.email,
                    "password": "wrong-password",
                },
                REMOTE_ADDR="203.0.113.57",
            )
        assert response.status_code == 422
        assert "该账号暂时限制登录" in response.content.decode()

    rows = security_event_list(is_admin=True, limit=100)
    restricted = next(
        item for item in rows if item.event_type == "LOGIN_RESTRICTION_APPLIED"
    )
    assert restricted.masked_ip.endswith(".x")
    detail = security_event_detail(event_id=restricted.id, is_admin=True)
    assert detail.client_ip == "203.0.113.57"
    with pytest.raises(PermissionError):
        security_event_list(is_admin=False)
