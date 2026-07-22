import pytest
from django.test import Client, RequestFactory

from apps.accounts.models import Account, IpBlock, LoginSession, SecurityEvent
from apps.accounts.network import ClientIpError, resolve_client_ip
from apps.accounts.queries.ip_blocks import ip_block_detail, ip_block_list
from apps.accounts.services.bootstrap import bootstrap_administrator
from apps.accounts.services.ip_blocks import IpBlockError, block_ip, unblock_ip
from config.environment import (
    ConfigurationError,
    load_trusted_proxy_cidrs,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def admin():
    return bootstrap_administrator(
        email="admin@kaj.test",
        initial_password="Strong-Initial-Password-410!",
        production=False,
    )


@pytest.fixture
def account():
    return Account.objects.create_account(
        email="network-user@kaj.test",
        password="Valid-password-1",
    )


def test_client_ip_trust_boundary_and_normalization() -> None:
    factory = RequestFactory()
    forged = factory.get(
        "/",
        REMOTE_ADDR="198.51.100.8",
        HTTP_X_KAJ_CLIENT_IP="203.0.113.9",
        HTTP_X_FORWARDED_FOR="192.0.2.9",
    )
    assert resolve_client_ip(forged, trusted_proxy_cidrs=("10.0.0.0/8",)) == (
        "198.51.100.8"
    )

    proxied_v4 = factory.get(
        "/",
        REMOTE_ADDR="10.0.0.4",
        HTTP_X_KAJ_CLIENT_IP="::ffff:203.0.113.10",
    )
    assert resolve_client_ip(proxied_v4, trusted_proxy_cidrs=("10.0.0.0/8",)) == (
        "203.0.113.10"
    )
    proxied_v6 = factory.get(
        "/",
        REMOTE_ADDR="10.0.0.4",
        HTTP_X_KAJ_CLIENT_IP="2001:0db8:0:0::11",
    )
    assert resolve_client_ip(proxied_v6, trusted_proxy_cidrs=("10.0.0.0/8",)) == (
        "2001:db8::11"
    )
    missing = factory.get("/", REMOTE_ADDR="10.0.0.4")
    with pytest.raises(ClientIpError):
        resolve_client_ip(missing, trusted_proxy_cidrs=("10.0.0.0/8",))
    ambiguous = factory.get(
        "/",
        REMOTE_ADDR="10.0.0.4",
        HTTP_X_KAJ_CLIENT_IP="203.0.113.10, 203.0.113.11",
    )
    with pytest.raises(ClientIpError):
        resolve_client_ip(ambiguous, trusted_proxy_cidrs=("10.0.0.0/8",))


def test_trusted_proxy_configuration_is_explicit_and_fail_closed() -> None:
    assert load_trusted_proxy_cidrs(
        {"KAJ_TRUSTED_PROXY_CIDRS": "10.2.3.4/8, 2001:db8::1/64"}
    ) == ("10.0.0.0/8", "2001:db8::/64")
    with pytest.raises(ConfigurationError):
        load_trusted_proxy_cidrs({}, required=True)
    with pytest.raises(ConfigurationError):
        load_trusted_proxy_cidrs({"KAJ_TRUSTED_PROXY_CIDRS": "0.0.0.0/0"})


def test_block_and_unblock_are_permanent_audited_transactions(admin) -> None:
    audit_rows = []

    def audit_ok(**kwargs):
        audit_rows.append(kwargs)

    blocked = block_ip(
        address="2001:0db8:0:0::40",
        note="重复撞库来源",
        actor_id=admin.id,
        client_ip="203.0.113.40",
        trace_code="KJ-IP-BLOCK",
        audit_writer=audit_ok,
    )
    blocked.refresh_from_db()
    assert blocked.address == "2001:db8::40"
    assert blocked.note == "重复撞库来源"
    assert blocked.unblocked_at is None
    audit = audit_rows[0]
    assert audit["target_id"] == blocked.id
    assert audit["after"] == {"active": True, "note_present": True}
    assert "重复撞库来源" not in str(audit["after"])
    event = SecurityEvent.objects.get(event_type="IP_BLOCK_APPLIED")
    assert event.client_ip == "203.0.113.40"
    assert event.safe_summary == {"action": "blocked"}
    assert blocked.address not in str(event.safe_summary)

    with pytest.raises(IpBlockError, match="已被封禁"):
        block_ip(
            address="2001:db8::40",
            note="",
            actor_id=admin.id,
            client_ip="203.0.113.40",
            trace_code="KJ-IP-DUPLICATE",
            audit_writer=audit_ok,
        )
    with pytest.raises(IpBlockError, match="当前管理连接"):
        block_ip(
            address="203.0.113.40",
            note="",
            actor_id=admin.id,
            client_ip="203.0.113.40",
            trace_code="KJ-IP-SELF",
            audit_writer=audit_ok,
        )

    released = unblock_ip(
        block_id=blocked.id,
        actor_id=admin.id,
        client_ip="203.0.113.40",
        trace_code="KJ-IP-UNBLOCK",
        audit_writer=audit_ok,
    )
    assert released.unblocked_at is not None
    assert [row["action"] for row in audit_rows] == [
        "accounts.ip_block.block",
        "accounts.ip_block.unblock",
    ]

    def reject_audit(**kwargs):
        del kwargs
        raise RuntimeError("audit unavailable")

    with pytest.raises(RuntimeError, match="audit unavailable"):
        block_ip(
            address="198.51.100.41",
            note="must roll back",
            actor_id=admin.id,
            client_ip="203.0.113.40",
            trace_code="KJ-IP-ROLLBACK",
            audit_writer=reject_audit,
        )
    assert not IpBlock.objects.filter(address="198.51.100.41").exists()


def test_blocked_network_is_guest_on_public_and_denied_before_session(
    account, admin
) -> None:
    raw_token, session = LoginSession.issue(
        account=account,
        remember=False,
        client_ip="203.0.113.70",
    )
    IpBlock.objects.create(
        address="203.0.113.70", note="never disclose", created_by=admin
    )
    client = Client()
    client.cookies["kaj_session"] = raw_token

    public = client.get("/", REMOTE_ADDR="203.0.113.70")
    assert public.status_code == 200
    body = public.content.decode()
    assert "你已登录" not in body
    assert "登录" in body

    private = client.get("/accounts/settings/", REMOTE_ADDR="203.0.113.70")
    assert private.status_code == 403
    private_body = private.content.decode()
    assert "当前网络暂时受限" in private_body
    assert "never disclose" not in private_body
    session.refresh_from_db()
    assert session.revoked_at is None

    before = LoginSession.objects.count()
    denied = client.post(
        "/accounts/login/",
        {
            "action": "password",
            "email": account.email,
            "password": "Valid-password-1",
        },
        REMOTE_ADDR="203.0.113.70",
    )
    assert denied.status_code == 403
    assert LoginSession.objects.count() == before

    spoofed = Client().post(
        "/accounts/login/",
        {
            "action": "password",
            "email": account.email,
            "password": "Valid-password-1",
        },
        REMOTE_ADDR="203.0.113.71",
        HTTP_X_FORWARDED_FOR="203.0.113.70",
        HTTP_X_KAJ_CLIENT_IP="203.0.113.70",
    )
    assert spoofed.status_code == 302


def test_ip_block_queries_mask_lists_and_protect_details(admin) -> None:
    first = IpBlock.objects.create(
        address="198.51.100.51",
        note="first source",
        created_by=admin,
    )
    IpBlock.objects.create(
        address="2001:db8::52",
        note="second source",
        created_by=admin,
    )
    rows = ip_block_list(is_admin=True, keyword="source")
    assert {row.masked_address for row in rows} == {
        "198.51.100.x",
        "2001:db8::/64",
    }
    assert all(row.address_digest for row in rows)
    assert not any("198.51.100.51" in str(row) for row in rows)
    detail = ip_block_detail(block_id=first.id, is_admin=True)
    assert detail.address == "198.51.100.51"
    with pytest.raises(PermissionError):
        ip_block_list(is_admin=False)
    with pytest.raises(PermissionError):
        ip_block_detail(block_id=first.id, is_admin=False)


def test_ip_block_admin_page_enforces_role_and_field_errors(admin, account) -> None:
    ordinary_raw, _ = LoginSession.issue(account=account, remember=False)
    ordinary = Client()
    ordinary.cookies["kaj_session"] = ordinary_raw
    assert ordinary.get("/admin/ip-blocks/").status_code == 403

    admin_raw, _ = LoginSession.issue(account=admin, remember=False)
    administrator = Client()
    administrator.cookies["kaj_session"] = admin_raw
    empty = administrator.get("/admin/ip-blocks/")
    assert empty.status_code == 200
    assert "当前没有封禁记录" in empty.content.decode()
    invalid = administrator.post(
        "/admin/ip-blocks/",
        {"action": "preview_block", "address": "not-an-ip", "note": ""},
        REMOTE_ADDR="203.0.113.60",
    )
    assert invalid.status_code == 422
    assert "请输入有效的 IP 地址" in invalid.content.decode()

    preview = administrator.post(
        "/admin/ip-blocks/",
        {
            "action": "preview_block",
            "address": "198.51.100.90",
            "note": "自动化测试来源",
        },
        REMOTE_ADDR="203.0.113.60",
    )
    assert preview.status_code == 200
    assert 'id="block-ip-dialog"' in preview.content.decode()
    assert "data-auto-modal" in preview.content.decode()
    saved = administrator.post(
        "/admin/ip-blocks/",
        {
            "action": "block",
            "address": "198.51.100.90",
            "note": "自动化测试来源",
            "confirm": "block",
        },
        REMOTE_ADDR="203.0.113.60",
    )
    assert saved.status_code == 302
    listing = administrator.get(saved["Location"])
    listing_body = listing.content.decode()
    assert "198.51.100.x" in listing_body
    assert "198.51.100.90" not in listing_body
    row = IpBlock.objects.get(address="198.51.100.90", unblocked_at__isnull=True)
    detail = administrator.get(f"/admin/ip-blocks/?detail={row.id}")
    assert "198.51.100.90" in detail.content.decode()
    confirmation = administrator.get(f"/admin/ip-blocks/?confirm={row.id}")
    assert "data-auto-modal" in confirmation.content.decode()
    released = administrator.post(
        "/admin/ip-blocks/",
        {"action": "unblock", "block_id": row.id, "confirm": "unblock"},
        REMOTE_ADDR="203.0.113.60",
    )
    assert released.status_code == 302
    row.refresh_from_db()
    assert row.unblocked_at is not None
