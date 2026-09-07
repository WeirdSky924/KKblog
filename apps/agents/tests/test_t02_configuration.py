from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import Account, RoleAssignment
from apps.agents.contracts import (
    DEFAULT_ENDPOINT_DAILY_TOKEN_LIMIT,
    DEFAULT_SITE_DAILY_TOKEN_LIMIT,
    EndpointRuntimeSettings,
)
from apps.agents.credentials import decrypt_api_key, encrypt_api_key
from apps.agents.models import (
    AgentEndpoint,
    AgentEndpointCheck,
    AgentInvocation,
    AgentProfile,
    AgentPromptRevision,
    AgentSitePolicy,
    AgentTokenAdjustment,
    AgentTokenLedger,
    AgentTokenReservation,
)
from apps.agents.public import (
    AgentCommandError,
    EndpointDraft,
    ProfileDraft,
    agent_endpoint_admin_items,
    agent_profile_available,
    create_agent_endpoint,
    create_agent_invocation,
    create_agent_profile,
    reserve_invocation_tokens,
    reset_token_usage,
    restore_default_token_limits,
    save_agent_prompt_revision,
    set_agent_profile_enabled,
    settle_token_reservation,
    switch_agent_prompt_revision,
    update_agent_endpoint,
    update_site_daily_token_limit,
)
from apps.core.observability.trace import new_trace_code

pytestmark = pytest.mark.django_db(transaction=True)


def _account(*, administrator: bool = False) -> Account:
    account = Account.objects.create_account(
        email=f"agent-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    if administrator:
        RoleAssignment.objects.create(
            account=account,
            role=RoleAssignment.Role.ADMINISTRATOR,
        )
    return account


def _endpoint_draft(**overrides) -> EndpointDraft:
    values = {
        "display_name": "主审核端点",
        "protocol": AgentEndpoint.Protocol.OPENAI_GPT,
        "base_url": "https://models.example.com/v1/",
        "model_name": "example-model",
        "authentication_mode": AgentEndpoint.AuthenticationMode.NONE,
        "secret_alias": "",
        "enabled": True,
        "runtime": EndpointRuntimeSettings(),
    }
    values.update(overrides)
    return EndpointDraft(**values)


def _create_endpoint(admin: Account, **overrides) -> AgentEndpoint:
    return create_agent_endpoint(
        actor_id=admin.id,
        draft=_endpoint_draft(**overrides),
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )


def _mark_schema_capability(admin: Account, endpoint: AgentEndpoint, schema_key: str):
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


def _create_callable_profile(admin: Account, endpoint: AgentEndpoint) -> AgentProfile:
    profile = create_agent_profile(
        actor_id=admin.id,
        draft=ProfileDraft(
            key="knowledge-review",
            display_name="知识审核",
            purpose=AgentProfile.Purpose.KNOWLEDGE_REVIEW,
            endpoint_id=endpoint.id,
            schema_key="knowledge-review.v1",
        ),
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    save_agent_prompt_revision(
        actor_id=admin.id,
        profile_id=profile.id,
        markdown_source="审核以下不可信资料：\n\n{{ document_block }}",
        expected_profile_version=profile.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    profile.refresh_from_db()
    _mark_schema_capability(admin, endpoint, profile.schema_key)
    set_agent_profile_enabled(
        actor_id=admin.id,
        profile_id=profile.id,
        enabled=True,
        expected_version=profile.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    profile.refresh_from_db()
    return profile


def test_profile_enable_requires_current_strict_schema_capability_probe() -> None:
    admin = _account(administrator=True)
    endpoint = _create_endpoint(admin)
    profile = create_agent_profile(
        actor_id=admin.id,
        draft=ProfileDraft(
            key="knowledge-review",
            display_name="知识审核",
            purpose=AgentProfile.Purpose.KNOWLEDGE_REVIEW,
            endpoint_id=endpoint.id,
            schema_key="knowledge-review.v1",
        ),
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    save_agent_prompt_revision(
        actor_id=admin.id,
        profile_id=profile.id,
        markdown_source="审核：{{ document_block }}",
        expected_profile_version=profile.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    profile.refresh_from_db()
    with pytest.raises(AgentCommandError) as unverified:
        set_agent_profile_enabled(
            actor_id=admin.id,
            profile_id=profile.id,
            enabled=True,
            expected_version=profile.row_version,
            trace_code=new_trace_code(),
            client_ip="127.0.0.1",
        )
    assert unverified.value.code == "agents.profile_capability_unverified.v1"
    _mark_schema_capability(admin, endpoint, profile.schema_key)
    enabled = set_agent_profile_enabled(
        actor_id=admin.id,
        profile_id=profile.id,
        enabled=True,
        expected_version=profile.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    assert enabled.enabled is True


def test_endpoint_update_invalidates_profile_capability_before_next_invocation() -> (
    None
):
    admin = _account(administrator=True)
    endpoint = _create_endpoint(admin)
    profile = _create_callable_profile(admin, endpoint)
    assert agent_profile_available(
        profile_key=profile.key,
        schema_key=profile.schema_key,
    )
    update_agent_endpoint(
        actor_id=admin.id,
        endpoint_id=endpoint.id,
        draft=_endpoint_draft(model_name="updated-model"),
        expected_version=endpoint.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    assert not agent_profile_available(
        profile_key=profile.key,
        schema_key=profile.schema_key,
    )
    with pytest.raises(AgentCommandError) as unavailable:
        create_agent_invocation(
            profile_key=profile.key,
            caller_type="knowledge_review",
            caller_id="document-after-endpoint-update",
            idempotency_key="review-after-endpoint-update",
            estimated_input_tokens=1_000,
        )
    assert unavailable.value.code == "agents.profile_capability_unverified.v1"


def test_runtime_defaults_and_cross_field_validation() -> None:
    runtime = EndpointRuntimeSettings()
    assert runtime.context_window_tokens == 131_072
    assert runtime.max_output_tokens == 8_192
    assert runtime.per_run_token_limit == 500_000
    assert runtime.request_timeout_seconds == 120
    assert runtime.concurrency_limit == 1
    assert runtime.endpoint_daily_token_limit == DEFAULT_ENDPOINT_DAILY_TOKEN_LIMIT

    invalid = EndpointRuntimeSettings(
        context_window_tokens=4_096,
        max_output_tokens=4_096,
    )
    with pytest.raises(AgentCommandError) as rejected:
        invalid.validate(site_daily_token_limit=DEFAULT_SITE_DAILY_TOKEN_LIMIT)
    assert rejected.value.code == "agents.runtime_limits_invalid.v1"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("context_window_tokens", 4_095),
        ("context_window_tokens", 2_000_001),
        ("max_output_tokens", 255),
        ("max_output_tokens", 131_073),
        ("per_run_token_limit", 9_999),
        ("per_run_token_limit", 5_000_001),
        ("request_timeout_seconds", 9),
        ("request_timeout_seconds", 1_801),
        ("concurrency_limit", 0),
        ("concurrency_limit", 6),
        ("endpoint_daily_token_limit", 49_999),
        ("endpoint_daily_token_limit", 50_000_001),
    ),
)
def test_runtime_hard_ranges_are_enforced(field: str, value: int) -> None:
    values = EndpointRuntimeSettings().as_dict()
    values[field] = value
    with pytest.raises(AgentCommandError):
        EndpointRuntimeSettings(**values).validate(
            site_daily_token_limit=DEFAULT_SITE_DAILY_TOKEN_LIMIT
        )


def test_runtime_timeout_accepts_thirty_minutes() -> None:
    runtime = EndpointRuntimeSettings(request_timeout_seconds=1_800)
    assert runtime.validate(site_daily_token_limit=DEFAULT_SITE_DAILY_TOKEN_LIMIT)


def test_only_administrator_can_create_endpoint_and_no_secret_is_stored() -> None:
    user = _account()
    with pytest.raises(AgentCommandError) as denied:
        _create_endpoint(user)
    assert denied.value.code == "agents.administrator_required.v1"

    admin = _account(administrator=True)
    endpoint = _create_endpoint(
        admin,
        authentication_mode=AgentEndpoint.AuthenticationMode.SECRET_ALIAS,
        secret_alias="PRIMARY_GPT",
    )
    assert endpoint.base_url == "https://models.example.com/v1"
    assert endpoint.secret_alias == "PRIMARY_GPT"
    assert not any(
        field.name in {"api_key", "secret", "authorization"}
        for field in AgentEndpoint._meta.fields
    )
    policy = AgentSitePolicy.objects.get(pk=1)
    assert policy.daily_token_limit == DEFAULT_SITE_DAILY_TOKEN_LIMIT
    with pytest.raises(AgentCommandError):
        agent_endpoint_admin_items(actor_id=user.id)
    assert (
        agent_endpoint_admin_items(actor_id=admin.id)[0].secret_alias == "PRIMARY_GPT"
    )


@pytest.mark.parametrize(
    ("protocol", "expected_base_url"),
    (
        (AgentEndpoint.Protocol.OPENAI_GPT, "https://api.openai.com/v1"),
        (AgentEndpoint.Protocol.OPENAI_DEEPSEEK, "https://api.deepseek.com"),
        (AgentEndpoint.Protocol.ANTHROPIC, "https://api.anthropic.com/v1"),
    ),
)
def test_endpoint_uses_provider_default_base_url_when_omitted(
    protocol: str, expected_base_url: str
) -> None:
    admin = _account(administrator=True)
    endpoint = _create_endpoint(admin, protocol=protocol, base_url="")
    assert endpoint.base_url == expected_base_url


def test_custom_api_key_is_encrypted_and_round_trips_without_plaintext_storage() -> (
    None
):
    ciphertext = encrypt_api_key("sk-custom-provider-key")
    assert ciphertext != "sk-custom-provider-key"
    assert "sk-custom-provider-key" not in ciphertext
    assert decrypt_api_key(ciphertext) == "sk-custom-provider-key"


def test_custom_api_key_create_preserve_rotate_and_clear() -> None:
    admin = _account(administrator=True)
    endpoint = _create_endpoint(
        admin,
        authentication_mode=AgentEndpoint.AuthenticationMode.CUSTOM_API_KEY,
        api_key="sk-first-provider-key",
    )
    first_ciphertext = endpoint.api_key_ciphertext
    assert first_ciphertext
    assert "sk-first-provider-key" not in first_ciphertext

    preserved = update_agent_endpoint(
        actor_id=admin.id,
        endpoint_id=endpoint.id,
        draft=_endpoint_draft(
            authentication_mode=AgentEndpoint.AuthenticationMode.CUSTOM_API_KEY,
            api_key="",
        ),
        expected_version=endpoint.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    assert preserved.api_key_ciphertext == first_ciphertext

    rotated = update_agent_endpoint(
        actor_id=admin.id,
        endpoint_id=endpoint.id,
        draft=_endpoint_draft(
            authentication_mode=AgentEndpoint.AuthenticationMode.CUSTOM_API_KEY,
            api_key="sk-rotated-provider-key",
        ),
        expected_version=preserved.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    assert rotated.api_key_ciphertext != first_ciphertext
    assert decrypt_api_key(rotated.api_key_ciphertext) == "sk-rotated-provider-key"

    cleared = update_agent_endpoint(
        actor_id=admin.id,
        endpoint_id=endpoint.id,
        draft=_endpoint_draft(
            authentication_mode=AgentEndpoint.AuthenticationMode.NONE,
        ),
        expected_version=rotated.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    assert cleared.api_key_ciphertext == ""


def test_endpoint_update_rejects_stale_version_and_site_limit_conflict() -> None:
    admin = _account(administrator=True)
    endpoint = _create_endpoint(admin)
    draft = _endpoint_draft(
        runtime=EndpointRuntimeSettings(endpoint_daily_token_limit=5_000_001)
    )
    with pytest.raises(AgentCommandError) as over_site:
        update_agent_endpoint(
            actor_id=admin.id,
            endpoint_id=endpoint.id,
            draft=draft,
            expected_version=endpoint.row_version,
            trace_code=new_trace_code(),
            client_ip="127.0.0.1",
        )
    assert over_site.value.code == "agents.runtime_limits_invalid.v1"

    with pytest.raises(AgentCommandError) as stale:
        update_agent_endpoint(
            actor_id=admin.id,
            endpoint_id=endpoint.id,
            draft=_endpoint_draft(display_name="已过期写入"),
            expected_version=endpoint.row_version + 1,
            trace_code=new_trace_code(),
            client_ip="127.0.0.1",
        )
    assert stale.value.code == "agents.configuration_conflict.v1"


def test_site_limit_update_and_restore_defaults_use_all_row_versions() -> None:
    admin = _account(administrator=True)
    endpoint = _create_endpoint(admin)
    policy = AgentSitePolicy.objects.get(pk=1)
    with pytest.raises(AgentCommandError) as conflict:
        update_site_daily_token_limit(
            actor_id=admin.id,
            daily_token_limit=1_000_000,
            expected_version=policy.row_version,
            trace_code=new_trace_code(),
            client_ip="127.0.0.1",
        )
    assert conflict.value.code == "agents.site_limit_conflict.v1"

    endpoint = update_agent_endpoint(
        actor_id=admin.id,
        endpoint_id=endpoint.id,
        draft=_endpoint_draft(
            runtime=EndpointRuntimeSettings(endpoint_daily_token_limit=500_000)
        ),
        expected_version=endpoint.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    policy = update_site_daily_token_limit(
        actor_id=admin.id,
        daily_token_limit=1_000_000,
        expected_version=policy.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    assert policy.daily_token_limit == 1_000_000

    restored = restore_default_token_limits(
        actor_id=admin.id,
        expected_site_version=policy.row_version,
        expected_endpoint_versions={str(endpoint.id): endpoint.row_version},
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    endpoint.refresh_from_db()
    assert restored.daily_token_limit == DEFAULT_SITE_DAILY_TOKEN_LIMIT
    assert endpoint.daily_token_limit == DEFAULT_ENDPOINT_DAILY_TOKEN_LIMIT


def test_prompt_revisions_are_immutable_and_invocation_snapshot_does_not_drift() -> (
    None
):
    admin = _account(administrator=True)
    endpoint = _create_endpoint(admin)
    profile = _create_callable_profile(admin, endpoint)
    first = profile.current_prompt
    second = save_agent_prompt_revision(
        actor_id=admin.id,
        profile_id=profile.id,
        markdown_source="第二版：{{ document_block }}",
        expected_profile_version=profile.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    profile.refresh_from_db()
    assert first.sequence == 1
    assert second.sequence == 2
    assert profile.current_prompt_id == second.id
    assert AgentPromptRevision.objects.get(pk=first.id).markdown_source.startswith(
        "审核以下"
    )

    invocation = create_agent_invocation(
        profile_key=profile.key,
        caller_type="knowledge_review",
        caller_id="document-001",
        idempotency_key="review-document-001-v1",
        estimated_input_tokens=1_000,
    )
    update_agent_endpoint(
        actor_id=admin.id,
        endpoint_id=endpoint.id,
        draft=_endpoint_draft(
            display_name="更新后的端点",
            model_name="new-model",
            runtime=EndpointRuntimeSettings(context_window_tokens=262_144),
        ),
        expected_version=endpoint.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    invocation.refresh_from_db()
    assert invocation.prompt_revision_id == second.id
    assert invocation.model_name_snapshot == "example-model"
    assert invocation.context_window_tokens_snapshot == 131_072


def test_prompt_history_is_immutable_and_can_be_selected_again() -> None:
    admin = _account(administrator=True)
    endpoint = _create_endpoint(admin)
    profile = _create_callable_profile(admin, endpoint)
    first = profile.current_prompt
    second = save_agent_prompt_revision(
        actor_id=admin.id,
        profile_id=profile.id,
        markdown_source="第二版：{{ document_block }}",
        expected_profile_version=profile.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    first.markdown_source = "不允许覆盖"
    with pytest.raises(RuntimeError, match="immutable"):
        first.save()
    with pytest.raises(RuntimeError, match="immutable"):
        first.delete()

    profile.refresh_from_db()
    switched = switch_agent_prompt_revision(
        actor_id=admin.id,
        profile_id=profile.id,
        prompt_revision_id=first.id,
        expected_version=profile.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    assert switched.current_prompt_id == first.id
    assert AgentPromptRevision.objects.get(pk=second.id).markdown_source.startswith(
        "第二版"
    )


def test_prompt_rejects_unknown_or_malformed_variables() -> None:
    admin = _account(administrator=True)
    endpoint = _create_endpoint(admin)
    profile = create_agent_profile(
        actor_id=admin.id,
        draft=ProfileDraft(
            key="knowledge-review",
            display_name="知识审核",
            purpose=AgentProfile.Purpose.KNOWLEDGE_REVIEW,
            endpoint_id=endpoint.id,
            schema_key="knowledge-review.v1",
        ),
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    for source in ("{{ unregistered_value }}", "{{ document_block"):
        with pytest.raises(AgentCommandError) as rejected:
            save_agent_prompt_revision(
                actor_id=admin.id,
                profile_id=profile.id,
                markdown_source=source,
                expected_profile_version=profile.row_version,
                trace_code=new_trace_code(),
                client_ip="127.0.0.1",
            )
        assert rejected.value.code == "agents.prompt_variable_invalid.v1"


def test_concurrent_prompt_save_rejects_stale_profile_version() -> None:
    admin = _account(administrator=True)
    endpoint = _create_endpoint(admin)
    profile = _create_callable_profile(admin, endpoint)
    stale_version = profile.row_version
    save_agent_prompt_revision(
        actor_id=admin.id,
        profile_id=profile.id,
        markdown_source="有效的新版本：{{ document_block }}",
        expected_profile_version=stale_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    with pytest.raises(AgentCommandError) as conflict:
        save_agent_prompt_revision(
            actor_id=admin.id,
            profile_id=profile.id,
            markdown_source="不应覆盖：{{ document_block }}",
            expected_profile_version=stale_version,
            trace_code=new_trace_code(),
            client_ip="127.0.0.1",
        )
    assert conflict.value.code == "agents.configuration_conflict.v1"


def test_database_rejects_prompt_sequence_and_invocation_idempotency_duplicates() -> (
    None
):
    admin = _account(administrator=True)
    endpoint = _create_endpoint(admin)
    profile = _create_callable_profile(admin, endpoint)
    with pytest.raises(IntegrityError), transaction.atomic():
        AgentPromptRevision.objects.create(
            profile=profile,
            sequence=1,
            markdown_source="duplicate",
            content_sha256="f" * 64,
            created_by=admin,
        )

    create_agent_invocation(
        profile_key=profile.key,
        caller_type="knowledge_review",
        caller_id="document-002",
        idempotency_key="same-key",
        estimated_input_tokens=1_000,
    )
    assert AgentInvocation.objects.count() == 1
    repeated = create_agent_invocation(
        profile_key=profile.key,
        caller_type="knowledge_review",
        caller_id="document-002",
        idempotency_key="same-key",
        estimated_input_tokens=1_000,
    )
    assert AgentInvocation.objects.count() == 1
    assert repeated.caller_id == "document-002"


def test_token_reservation_settlement_and_endpoint_reset_are_ledger_backed() -> None:
    admin = _account(administrator=True)
    endpoint = _create_endpoint(admin)
    profile = _create_callable_profile(admin, endpoint)
    invocation = create_agent_invocation(
        profile_key=profile.key,
        caller_type="knowledge_review",
        caller_id="document-003",
        idempotency_key="review-document-003-v1",
        estimated_input_tokens=1_000,
    )
    now = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    reservation = reserve_invocation_tokens(
        invocation_id=invocation.id,
        requested_tokens=500_000,
        idempotency_key="reserve-document-003-v1",
        lease_expires_at=now + timedelta(minutes=5),
        now=now,
    )
    assert reservation.status == AgentTokenReservation.Status.ACTIVE
    assert AgentTokenLedger.objects.count() == 2
    assert (
        reserve_invocation_tokens(
            invocation_id=invocation.id,
            requested_tokens=500_000,
            idempotency_key="reserve-document-003-v1",
            lease_expires_at=now + timedelta(minutes=5),
            now=now,
        ).id
        == reservation.id
    )

    settle_token_reservation(reservation_id=reservation.id, actual_tokens=125_000)
    reservation.refresh_from_db()
    assert reservation.status == AgentTokenReservation.Status.SETTLED
    assert reservation.settled_tokens == 125_000
    assert set(AgentTokenLedger.objects.values_list("settled_tokens", flat=True)) == {
        125_000
    }

    reset_token_usage(
        actor_id=admin.id,
        scope="endpoint",
        endpoint_id=endpoint.id,
        reason="管理员测试重置",
        idempotency_key="reset-endpoint-20260816",
        now=now,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    assert AgentTokenAdjustment.objects.count() == 2
    assert sum(AgentTokenAdjustment.objects.values_list("amount", flat=True)) == (
        -250_000
    )


def test_reset_keeps_active_reservations_and_adjustment_idempotency() -> None:
    admin = _account(administrator=True)
    endpoint = _create_endpoint(admin)
    profile = _create_callable_profile(admin, endpoint)
    invocation = create_agent_invocation(
        profile_key=profile.key,
        caller_type="knowledge_review",
        caller_id="document-004",
        idempotency_key="review-document-004-v1",
        estimated_input_tokens=1_000,
    )
    now = datetime(2026, 8, 16, 13, 0, tzinfo=UTC)
    reservation = reserve_invocation_tokens(
        invocation_id=invocation.id,
        requested_tokens=500_000,
        idempotency_key="reserve-document-004-v1",
        lease_expires_at=now + timedelta(minutes=5),
        now=now,
    )
    reset_token_usage(
        actor_id=admin.id,
        scope="site",
        endpoint_id=None,
        reason="保留在途额度",
        idempotency_key="reset-site-20260816",
        now=now,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    reservation.refresh_from_db()
    assert reservation.status == AgentTokenReservation.Status.ACTIVE
    assert AgentTokenAdjustment.objects.count() == 0
    reset_token_usage(
        actor_id=admin.id,
        scope="site",
        endpoint_id=None,
        reason="保留在途额度",
        idempotency_key="reset-site-20260816",
        now=now,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    assert AgentTokenAdjustment.objects.count() == 0
