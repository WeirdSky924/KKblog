from datetime import UTC, datetime
from uuid import uuid4

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Account, LoginSession, RoleAssignment
from apps.agents.contracts import EndpointRuntimeSettings
from apps.agents.models import AgentEndpoint, AgentEndpointCheck, AgentProfile
from apps.agents.public import (
    EndpointDraft,
    ProfileDraft,
    create_agent_endpoint,
    create_agent_profile,
    save_agent_prompt_revision,
)
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from config.environment import AgentProviderEnvironment

pytestmark = pytest.mark.django_db(transaction=True)


def _account_client(client, *, administrator: bool):
    account = Account.objects.create_account(
        email=f"agent-admin-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    if administrator:
        RoleAssignment.objects.create(
            account=account,
            role=RoleAssignment.Role.ADMINISTRATOR,
        )
    token, _session = LoginSession.issue(
        account=account,
        remember=False,
        client_ip="127.0.0.1",
    )
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token
    return account


def _endpoint(admin, *, enabled=True):
    return create_agent_endpoint(
        actor_id=admin.id,
        draft=EndpointDraft(
            display_name=f"Admin endpoint {uuid4()}",
            protocol=AgentEndpoint.Protocol.OPENAI_GPT,
            base_url="https://api.example.com/v1",
            model_name="admin-model",
            authentication_mode=AgentEndpoint.AuthenticationMode.NONE,
            enabled=enabled,
            runtime=EndpointRuntimeSettings(),
        ),
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )


def _profile(admin, endpoint):
    return create_agent_profile(
        actor_id=admin.id,
        draft=ProfileDraft(
            key=f"knowledge-review-{uuid4().hex[:8]}",
            display_name="知识审核",
            purpose=AgentProfile.Purpose.KNOWLEDGE_REVIEW,
            endpoint_id=endpoint.id,
            schema_key="knowledge-review.v1",
        ),
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )


def _mark_schema_capability(admin, endpoint, schema_key):
    now = datetime.now(UTC)
    return AgentEndpointCheck.objects.create(
        endpoint=endpoint,
        requested_by_id=admin.id,
        idempotency_key=f"test-capability:{uuid4()}",
        state=AgentEndpointCheck.State.SUCCEEDED,
        endpoint_row_version_snapshot=endpoint.row_version,
        protocol_snapshot=endpoint.protocol,
        base_url_snapshot=endpoint.base_url,
        model_name_snapshot=endpoint.model_name,
        schema_key_snapshot=schema_key,
        capability_strategy="native",
        capability_state="SCHEMA_SUPPORTED",
        authentication_mode_snapshot=endpoint.authentication_mode,
        secret_alias_snapshot=endpoint.secret_alias,
        api_key_ciphertext_snapshot=endpoint.api_key_ciphertext,
        request_timeout_seconds_snapshot=endpoint.request_timeout_seconds,
        concurrency_limit_snapshot=endpoint.concurrency_limit,
        endpoint_daily_token_limit_snapshot=endpoint.daily_token_limit,
        site_daily_token_limit_snapshot=5_000_000,
        token_budget=2_048,
        attempt_count=1,
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        requested_at=now,
        started_at=now,
        completed_at=now,
    )


def _endpoint_form_data(**overrides):
    values = {
        "action": "endpoint_create",
        "display_name": "Primary endpoint",
        "protocol": AgentEndpoint.Protocol.OPENAI_GPT,
        "base_url": "https://api.example.com/v1",
        "model_name": "primary-model",
        "authentication_mode": AgentEndpoint.AuthenticationMode.NONE,
        "secret_alias": "",
        "enabled": "on",
        "context_window_tokens": "131072",
        "max_output_tokens": "8192",
        "per_run_token_limit": "500000",
        "request_timeout_seconds": "120",
        "concurrency_limit": "1",
        "endpoint_daily_token_limit": "2000000",
        "input_price_per_million_tokens": "",
        "output_price_per_million_tokens": "",
    }
    values.update(overrides)
    return values


def test_agent_pages_are_admin_only_and_never_render_secret_values(
    client, settings
) -> None:
    admin = _account_client(client, administrator=True)
    settings.AGENT_PROVIDER_ENVIRONMENT = AgentProviderEnvironment(
        secrets={"PRIMARY_GPT": "synthetic-secret-value"},
        internal_allowlist=(),
    )
    endpoint = create_agent_endpoint(
        actor_id=admin.id,
        draft=EndpointDraft(
            display_name="Secret alias endpoint",
            protocol=AgentEndpoint.Protocol.OPENAI_GPT,
            base_url="https://api.example.com/v1",
            model_name="safe-model",
            authentication_mode=AgentEndpoint.AuthenticationMode.SECRET_ALIAS,
            secret_alias="PRIMARY_GPT",
            runtime=EndpointRuntimeSettings(),
        ),
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    _profile(admin, endpoint)

    endpoints = client.get(reverse("admin:agent-endpoints"))
    profiles = client.get(reverse("admin:agent-profiles"))
    endpoint_body = endpoints.content.decode()
    assert endpoints.status_code == 200
    assert profiles.status_code == 200
    assert "AI 配置" in endpoint_body
    assert "PRIMARY_GPT" in endpoint_body
    assert "synthetic-secret-value" not in endpoint_body
    assert "Endpoint 与用量" in endpoint_body
    assert "AGENT 与 Prompt" in profiles.content.decode()

    ordinary_client = Client()
    _account_client(ordinary_client, administrator=False)
    assert ordinary_client.get(reverse("admin:agent-endpoints")).status_code == 403
    assert ordinary_client.get(reverse("admin:agent-profiles")).status_code == 403


def test_endpoint_form_retains_invalid_input_and_persists_valid_create(client) -> None:
    _account_client(client, administrator=True)
    invalid = client.post(
        reverse("admin:agent-endpoints"),
        _endpoint_form_data(
            display_name="Retained endpoint",
            max_output_tokens="131072",
            context_window_tokens="4096",
        ),
    )
    body = invalid.content.decode()
    assert invalid.status_code == 422
    assert "Retained endpoint" in body
    assert "Endpoint 运行参数超出允许范围或互相冲突" in body
    assert AgentEndpoint.objects.count() == 0

    created = client.post(
        reverse("admin:agent-endpoints"),
        _endpoint_form_data(),
    )
    assert created.status_code == 302
    endpoint = AgentEndpoint.objects.get(display_name="Primary endpoint")
    assert endpoint.enabled is True
    assert endpoint.model_name == "primary-model"


def test_endpoint_create_dialog_has_valid_advanced_defaults(client) -> None:
    _account_client(client, administrator=True)
    response = client.get(
        reverse("admin:agent-endpoints"),
        {"dialog": "endpoint-create"},
    )
    body = response.content.decode()
    assert response.status_code == 200
    assert 'name="context_window_tokens" value="131072"' in body
    assert 'name="max_output_tokens" value="8192"' in body
    assert 'name="per_run_token_limit" value="500000"' in body
    assert 'name="request_timeout_seconds" value="120"' in body
    assert 'name="concurrency_limit" value="1"' in body
    assert 'name="endpoint_daily_token_limit" value="2000000"' in body


def test_endpoint_form_uses_provider_defaults_and_explains_missing_secrets(
    client, settings
) -> None:
    _account_client(client, administrator=True)
    settings.AGENT_PROVIDER_ENVIRONMENT = AgentProviderEnvironment(
        secrets={}, internal_allowlist=()
    )
    page = client.get(reverse("admin:agent-endpoints"))
    assert page.status_code == 200
    assert "服务器密钥别名尚未加载" in page.content.decode()

    response = client.post(
        reverse("admin:agent-endpoints"),
        _endpoint_form_data(base_url=""),
    )
    assert response.status_code == 302
    endpoint = AgentEndpoint.objects.get(display_name="Primary endpoint")
    assert endpoint.base_url == "https://api.openai.com/v1"


def test_endpoint_form_accepts_custom_api_key_without_rendering_it(client) -> None:
    _account_client(client, administrator=True)
    response = client.post(
        reverse("admin:agent-endpoints"),
        _endpoint_form_data(
            display_name="Custom endpoint",
            authentication_mode=AgentEndpoint.AuthenticationMode.CUSTOM_API_KEY,
            api_key="sk-admin-custom-key",
        ),
    )
    assert response.status_code == 302
    endpoint = AgentEndpoint.objects.get(display_name="Custom endpoint")
    assert endpoint.api_key_ciphertext
    assert "sk-admin-custom-key" not in endpoint.api_key_ciphertext
    page = client.get(reverse("admin:agent-endpoints"))
    assert page.status_code == 200
    assert "sk-admin-custom-key" not in page.content.decode()


def test_connection_check_post_only_queues_persistent_check(
    client, monkeypatch
) -> None:
    admin = _account_client(client, administrator=True)
    endpoint = _endpoint(admin)
    dispatched = []
    monkeypatch.setattr(
        "apps.administration.views.agent_endpoints.dispatch_endpoint_check",
        dispatched.append,
    )
    response = client.post(
        reverse("admin:agent-endpoints"),
        {
            "action": "endpoint_check",
            "endpoint_id": endpoint.id,
            "expected_version": endpoint.row_version,
            "request_id": new_ulid(),
            "confirm": "endpoint_check",
        },
    )
    assert response.status_code == 302
    check = AgentEndpointCheck.objects.get(endpoint=endpoint)
    assert check.state == AgentEndpointCheck.State.PENDING
    assert dispatched == [check.id]


def test_connection_check_can_probe_a_selected_pending_profile_schema(
    client, monkeypatch
) -> None:
    admin = _account_client(client, administrator=True)
    endpoint = _endpoint(admin)
    profile = _profile(admin, endpoint)
    save_agent_prompt_revision(
        actor_id=admin.id,
        profile_id=profile.id,
        markdown_source="审核：{{ document_block }}",
        expected_profile_version=profile.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    profile.refresh_from_db()
    dispatched = []
    monkeypatch.setattr(
        "apps.administration.views.agent_endpoints.dispatch_endpoint_check",
        dispatched.append,
    )
    response = client.post(
        reverse("admin:agent-endpoints"),
        {
            "action": "endpoint_check",
            "endpoint_id": endpoint.id,
            "expected_version": endpoint.row_version,
            "request_id": new_ulid(),
            "confirm": "endpoint_check",
            "profile_key": profile.key,
        },
    )
    assert response.status_code == 302
    check = AgentEndpointCheck.objects.get(endpoint=endpoint)
    assert check.schema_key_snapshot == profile.schema_key
    assert dispatched == [check.id]


def test_connection_check_rejects_profile_from_another_endpoint(client) -> None:
    admin = _account_client(client, administrator=True)
    endpoint = _endpoint(admin)
    other_endpoint = _endpoint(admin)
    profile = _profile(admin, other_endpoint)
    response = client.post(
        reverse("admin:agent-endpoints"),
        {
            "action": "endpoint_check",
            "endpoint_id": endpoint.id,
            "expected_version": endpoint.row_version,
            "request_id": new_ulid(),
            "confirm": "endpoint_check",
            "profile_key": profile.key,
        },
    )
    assert response.status_code == 422
    assert AgentEndpointCheck.objects.count() == 0


def test_endpoint_usage_reset_validation_retains_dialog_and_focus_target(
    client,
) -> None:
    admin = _account_client(client, administrator=True)
    endpoint = _endpoint(admin)

    response = client.post(
        reverse("admin:agent-endpoints"),
        {
            "action": "token_reset",
            "scope": "ENDPOINT",
            "endpoint_id": endpoint.id,
            "expected_ledger_version": 0,
            "reason": "",
            "operation_id": new_ulid(),
            "confirm": "token_reset",
        },
    )

    body = response.content.decode()
    assert response.status_code == 422
    assert 'id="agent-confirm-dialog"' in body
    assert "这个字段是必填项" in body
    assert f'data-dialog-return-focus="token-reset-{endpoint.id}"' in body


def test_profile_update_uses_existing_key_when_disabled_input_is_omitted(
    client,
) -> None:
    admin = _account_client(client, administrator=True)
    endpoint = _endpoint(admin)
    profile = _profile(admin, endpoint)
    save_agent_prompt_revision(
        actor_id=admin.id,
        profile_id=profile.id,
        markdown_source="# 审核规则\n\n{{ document_block }}",
        expected_profile_version=profile.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    profile.refresh_from_db()
    _mark_schema_capability(admin, endpoint, profile.schema_key)

    response = client.post(
        reverse("admin:agent-profiles"),
        {
            "action": "profile_update",
            "profile_id": profile.id,
            "expected_version": profile.row_version,
            "display_name": "已启用的知识审核",
            "purpose": profile.purpose,
            "endpoint_id": endpoint.id,
            "schema_key": profile.schema_key,
            "enabled": "on",
        },
    )

    assert response.status_code == 302
    profile.refresh_from_db()
    assert profile.key.startswith("knowledge-review-")
    assert profile.display_name == "已启用的知识审核"
    assert profile.enabled is True


def test_prompt_preview_is_sanitized_and_revision_switch_reads_back(client) -> None:
    admin = _account_client(client, administrator=True)
    endpoint = _endpoint(admin)
    profile = _profile(admin, endpoint)
    source_one = "# 审核规则\n\n<script>alert(1)</script>\n\n{{ document_block }}"

    preview = client.post(
        reverse("admin:agent-profiles"),
        {
            "action": "prompt_preview",
            "profile_id": profile.id,
            "expected_version": profile.row_version,
            "markdown_source": source_one,
        },
    )
    preview_body = preview.content.decode()
    assert preview.status_code == 200
    assert "Markdown 预览" in preview_body
    assert "<script>alert(1)</script>" not in preview_body
    assert "审核规则" in preview_body

    saved_one = client.post(
        reverse("admin:agent-profiles"),
        {
            "action": "prompt_save",
            "profile_id": profile.id,
            "expected_version": profile.row_version,
            "markdown_source": source_one,
        },
    )
    assert saved_one.status_code == 302
    profile.refresh_from_db()
    first_revision = profile.current_prompt
    assert first_revision.sequence == 1

    source_two = "# 新审核规则\n\n{{ document_block }}"
    saved_two = client.post(
        reverse("admin:agent-profiles"),
        {
            "action": "prompt_save",
            "profile_id": profile.id,
            "expected_version": profile.row_version,
            "markdown_source": source_two,
        },
    )
    assert saved_two.status_code == 302
    profile.refresh_from_db()
    assert profile.current_prompt.sequence == 2

    switched = client.post(
        reverse("admin:agent-profiles"),
        {
            "action": "prompt_switch",
            "profile_id": profile.id,
            "revision_id": first_revision.id,
            "expected_version": profile.row_version,
            "confirm": "prompt_switch",
        },
    )
    assert switched.status_code == 302
    profile.refresh_from_db()
    assert profile.current_prompt_id == first_revision.id
    assert profile.current_prompt.markdown_source == source_one


def test_prompt_switch_errors_retain_confirmation_dialog_and_focus(client) -> None:
    admin = _account_client(client, administrator=True)
    endpoint = _endpoint(admin)
    profile = _profile(admin, endpoint)
    first_revision = save_agent_prompt_revision(
        actor_id=admin.id,
        profile_id=profile.id,
        markdown_source="# 第一版\n\n{{ document_block }}",
        expected_profile_version=profile.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    profile.refresh_from_db()

    invalid = client.post(
        reverse("admin:agent-profiles"),
        {
            "action": "prompt_switch",
            "profile_id": profile.id,
            "revision_id": first_revision.id,
            "expected_version": profile.row_version,
            "confirm": "invalid",
        },
    )
    invalid_body = invalid.content.decode()
    assert invalid.status_code == 422
    assert 'id="agent-prompt-switch-dialog"' in invalid_body
    assert "请重新确认 Prompt 版本切换" in invalid_body
    assert f'data-dialog-return-focus="prompt-edit-{profile.id}"' in invalid_body

    stale_version = profile.row_version
    save_agent_prompt_revision(
        actor_id=admin.id,
        profile_id=profile.id,
        markdown_source="# 第二版\n\n{{ document_block }}",
        expected_profile_version=stale_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    conflict = client.post(
        reverse("admin:agent-profiles"),
        {
            "action": "prompt_switch",
            "profile_id": profile.id,
            "revision_id": first_revision.id,
            "expected_version": stale_version,
            "confirm": "prompt_switch",
        },
    )
    conflict_body = conflict.content.decode()
    assert conflict.status_code == 409
    assert 'id="agent-prompt-switch-dialog"' in conflict_body
    assert f'data-dialog-return-focus="prompt-edit-{profile.id}"' in conflict_body


def test_agent_management_posts_require_csrf() -> None:
    csrf_client = Client(enforce_csrf_checks=True)
    _account_client(csrf_client, administrator=True)
    endpoint_response = csrf_client.post(
        reverse("admin:agent-endpoints"),
        _endpoint_form_data(),
    )
    profile_response = csrf_client.post(
        reverse("admin:agent-profiles"),
        {"action": "profile_create"},
    )
    assert endpoint_response.status_code == 403
    assert profile_response.status_code == 403
