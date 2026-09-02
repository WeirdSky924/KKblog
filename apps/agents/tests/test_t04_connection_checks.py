import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apps.accounts.models import Account, RoleAssignment
from apps.agents.contracts import EndpointRuntimeSettings
from apps.agents.gateway import AgentGateway
from apps.agents.models import (
    AgentEndpoint,
    AgentEndpointCheck,
    AgentInvocation,
    AgentProfile,
    AgentTokenLedger,
    AgentTokenReservation,
)
from apps.agents.providers.fake import (
    DeterministicFakeProviderTransport,
    ScriptedProviderTransport,
)
from apps.agents.providers.http import ProviderTransportError
from apps.agents.public import (
    EndpointDraft,
    ProfileDraft,
    create_agent_endpoint,
    create_agent_profile,
    execute_agent_endpoint_check,
    mark_agent_endpoint_check_final_failed,
    recover_expired_token_reservations,
    request_agent_endpoint_check,
    reset_token_usage,
    save_agent_prompt_revision,
    update_agent_endpoint,
)
from apps.agents.tasks import CHECK_ENDPOINT_TASK_NAME, check_endpoint_task
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.operations.models import TaskRun, TaskRunStatus
from apps.operations.public import RetryableTaskError

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
PUBLIC_ADDRESS = "93.184.216.34"


pytestmark = pytest.mark.django_db(transaction=True)


def _admin() -> Account:
    account = Account.objects.create_account(
        email=f"agent-check-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    RoleAssignment.objects.create(
        account=account, role=RoleAssignment.Role.ADMINISTRATOR
    )
    return account


def _endpoint(admin: Account) -> AgentEndpoint:
    return create_agent_endpoint(
        actor_id=admin.id,
        draft=EndpointDraft(
            display_name=f"Check endpoint {uuid4()}",
            protocol=AgentEndpoint.Protocol.OPENAI_GPT,
            base_url="https://api.example.com/v1",
            model_name="check-model",
            authentication_mode=AgentEndpoint.AuthenticationMode.NONE,
            enabled=False,
            runtime=EndpointRuntimeSettings(),
        ),
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )


def _gateway(transport) -> AgentGateway:
    return AgentGateway(
        transport=transport,
        resolver=lambda _hostname, _port: (PUBLIC_ADDRESS,),
        secret_registry={},
        sleeper=lambda _seconds: None,
        clock=lambda: NOW,
    )


def _request(
    admin,
    endpoint,
    *,
    key="check-request-001",
    dispatcher=lambda _id: None,
    profile_key="",
):
    return request_agent_endpoint_check(
        actor_id=admin.id,
        endpoint_id=endpoint.id,
        expected_endpoint_version=endpoint.row_version,
        idempotency_key=key,
        dispatcher=dispatcher,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
        profile_key=profile_key,
        now=NOW,
    )


def test_request_is_admin_only_idempotent_rate_limited_and_dispatched(
    django_capture_on_commit_callbacks,
) -> None:
    admin = _admin()
    endpoint = _endpoint(admin)
    dispatched = []
    with django_capture_on_commit_callbacks(execute=True):
        check = _request(admin, endpoint, dispatcher=dispatched.append)

    assert dispatched == [check.id]
    assert check.state == AgentEndpointCheck.State.PENDING
    assert check.endpoint_row_version_snapshot == endpoint.row_version
    assert check.base_url_snapshot == endpoint.base_url
    assert check.secret_alias_snapshot == ""
    assert check.token_budget == 2_048

    with django_capture_on_commit_callbacks(execute=True):
        repeated = _request(admin, endpoint, dispatcher=dispatched.append)
    assert repeated.id == check.id
    assert dispatched == [check.id]

    with pytest.raises(Exception) as rate_limited:
        _request(admin, endpoint, key="check-request-002")
    assert getattr(rate_limited.value, "code", None) == "agents.check_rate_limited.v1"
    assert AgentEndpointCheck.objects.count() == 1

    ordinary = Account.objects.create_account(
        email=f"ordinary-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    with pytest.raises(Exception) as denied:
        request_agent_endpoint_check(
            actor_id=ordinary.id,
            endpoint_id=endpoint.id,
            expected_endpoint_version=endpoint.row_version,
            idempotency_key="check-request-denied",
            dispatcher=lambda _id: None,
            trace_code=new_trace_code(),
            client_ip="127.0.0.1",
            now=NOW + timedelta(minutes=2),
        )
    assert getattr(denied.value, "code", None) == "agents.administrator_required.v1"
    assert AgentEndpointCheck.objects.count() == 1


def test_success_uses_snapshot_and_settles_trusted_usage() -> None:
    admin = _admin()
    endpoint = _endpoint(admin)
    check = _request(admin, endpoint)
    update_agent_endpoint(
        actor_id=admin.id,
        endpoint_id=endpoint.id,
        draft=EndpointDraft(
            display_name=endpoint.display_name,
            protocol=AgentEndpoint.Protocol.OPENAI_DEEPSEEK,
            base_url="https://changed.example.com/v2",
            model_name="changed-model",
            authentication_mode=AgentEndpoint.AuthenticationMode.NONE,
            enabled=False,
            runtime=EndpointRuntimeSettings(),
        ),
        expected_version=endpoint.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    fake = DeterministicFakeProviderTransport(
        value={"ok": True}, input_tokens=10, output_tokens=5
    )
    transport = ScriptedProviderTransport((fake,))

    result = execute_agent_endpoint_check(
        check_id=check.id,
        task_run_id=new_ulid(),
        gateway=_gateway(transport),
        now=NOW + timedelta(seconds=1),
    )

    assert result.state == AgentEndpointCheck.State.SUCCEEDED
    assert result.total_tokens == 15
    assert result.attempt_count == 1
    assert transport.call_count == 1
    request = transport.last_request
    assert request is not None
    assert request.url == "https://api.example.com/v1/chat/completions"
    payload = json.loads(request.body)
    assert payload["model"] == "check-model"
    assert "response_format" not in payload
    assert "tools" not in payload
    assert result.capability_strategy == "connectivity"
    assert result.capability_adapter_version.startswith("langchain-openai-")
    reservation = AgentTokenReservation.objects.get(endpoint_check=result)
    assert reservation.status == AgentTokenReservation.Status.SETTLED
    assert reservation.settled_tokens == 15
    assert set(AgentTokenLedger.objects.values_list("settled_tokens", flat=True)) == {
        15
    }
    assert AgentInvocation.objects.count() == 0


def test_profile_schema_probe_reads_back_strict_capability_facts() -> None:
    admin = _admin()
    endpoint = _endpoint(admin)
    endpoint.enabled = True
    endpoint.save(update_fields=("enabled", "updated_at"))
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
    check = _request(admin, endpoint, profile_key=profile.key)
    result = execute_agent_endpoint_check(
        check_id=check.id,
        task_run_id=new_ulid(),
        gateway=AgentGateway(
            transport=DeterministicFakeProviderTransport(
                value={
                    "verdict": "APPROVED",
                    "reason_code": "ok",
                    "summary": "safe",
                    "risk_categories": [],
                },
                input_tokens=10,
                output_tokens=8,
            ),
            resolver=lambda _hostname, _port: (PUBLIC_ADDRESS,),
            secret_registry={},
            sleeper=lambda _seconds: None,
            clock=lambda: NOW,
        ),
        now=NOW + timedelta(seconds=1),
    )
    assert result.state == AgentEndpointCheck.State.SUCCEEDED
    assert result.schema_key_snapshot == profile.schema_key
    assert result.capability_state == "SCHEMA_SUPPORTED"
    assert result.capability_strategy == "native"
    assert result.capability_adapter_version.startswith("langchain-openai-")
    assert result.total_tokens == 18


def test_retry_reuses_reservation_and_uncertain_usage_settles_full_budget() -> None:
    admin = _admin()
    endpoint = _endpoint(admin)
    check = _request(admin, endpoint)
    failed_transport = ScriptedProviderTransport(
        (ProviderTransportError("agents.request_timeout.v1", retryable=True),)
    )

    task_run_id = new_ulid()
    with pytest.raises(RetryableTaskError):
        execute_agent_endpoint_check(
            check_id=check.id,
            task_run_id=task_run_id,
            gateway=_gateway(failed_transport),
            now=NOW + timedelta(seconds=1),
        )

    check.refresh_from_db()
    assert check.state == AgentEndpointCheck.State.RUNNING
    assert check.usage_uncertain is True
    reservation = AgentTokenReservation.objects.get(endpoint_check=check)
    assert reservation.status == AgentTokenReservation.Status.ACTIVE

    succeeded = execute_agent_endpoint_check(
        check_id=check.id,
        task_run_id=task_run_id,
        gateway=_gateway(DeterministicFakeProviderTransport(value={"ok": True})),
        now=NOW + timedelta(minutes=2),
    )
    reservation.refresh_from_db()
    assert succeeded.state == AgentEndpointCheck.State.SUCCEEDED
    assert succeeded.attempt_count == 2
    assert succeeded.total_tokens is None
    assert reservation.status == AgentTokenReservation.Status.SETTLED
    assert reservation.settled_tokens == check.token_budget


def test_final_task_failure_closes_check_without_quota_charge() -> None:
    admin = _admin()
    endpoint = _endpoint(admin)
    check = _request(admin, endpoint)
    transport = ScriptedProviderTransport(
        (ProviderTransportError("agents.request_network_failed.v1", retryable=True),)
    )
    with pytest.raises(RetryableTaskError):
        execute_agent_endpoint_check(
            check_id=check.id,
            task_run_id=new_ulid(),
            gateway=_gateway(transport),
            now=NOW + timedelta(seconds=1),
        )

    result = mark_agent_endpoint_check_final_failed(
        check_id=check.id,
        safe_error_code="agents.request_network_failed.v1",
        completed_at=NOW + timedelta(minutes=10),
    )
    reservation = AgentTokenReservation.objects.get(endpoint_check=result)
    assert result.state == AgentEndpointCheck.State.FAILED
    assert result.safe_error_code == "agents.request_network_failed.v1"
    assert reservation.status == AgentTokenReservation.Status.SETTLED
    assert reservation.settled_tokens == 0


def test_celery_entry_tracks_task_run_and_persists_success(monkeypatch) -> None:
    admin = _admin()
    endpoint = _endpoint(admin)
    check = _request(admin, endpoint)
    gateway = _gateway(
        DeterministicFakeProviderTransport(
            value={"ok": True}, input_tokens=8, output_tokens=5
        )
    )
    monkeypatch.setattr("apps.agents.tasks.build_agent_gateway", lambda: gateway)

    response = check_endpoint_task.apply(
        args=(str(check.id),), task_id=str(uuid4())
    ).get()

    check.refresh_from_db()
    task_run = TaskRun.objects.get(task_name=CHECK_ENDPOINT_TASK_NAME)
    reservation = AgentTokenReservation.objects.get(endpoint_check=check)
    assert response == {
        "status": "succeeded",
        "result_ref": f"agent-check:{check.id}:succeeded",
    }
    assert task_run.business_object == f"agent-check:{check.id}"
    assert task_run.idempotency_key == task_run.business_object
    assert task_run.status == TaskRunStatus.SUCCEEDED
    assert check.task_run_id == task_run.run_id
    assert check.state == AgentEndpointCheck.State.SUCCEEDED
    assert check.total_tokens == 13
    assert reservation.status == AgentTokenReservation.Status.SETTLED
    assert reservation.settled_tokens == 13


def test_recovery_does_not_charge_expired_running_check() -> None:
    admin = _admin()
    endpoint = _endpoint(admin)
    check = _request(admin, endpoint)
    with pytest.raises(RetryableTaskError):
        execute_agent_endpoint_check(
            check_id=check.id,
            task_run_id=new_ulid(),
            gateway=_gateway(
                ScriptedProviderTransport(
                    (
                        ProviderTransportError(
                            "agents.request_timeout.v1", retryable=True
                        ),
                    )
                )
            ),
            now=NOW + timedelta(seconds=1),
        )

    result = recover_expired_token_reservations(
        now=NOW + timedelta(hours=1, seconds=2), batch_size=10
    )

    check.refresh_from_db()
    reservation = AgentTokenReservation.objects.get(endpoint_check=check)
    assert result.conservative_count == 0
    assert result.released_count == 0
    assert check.state == AgentEndpointCheck.State.FAILED
    assert check.usage_uncertain is True
    assert check.safe_error_code == "agents.endpoint_check_lease_expired.v1"
    assert reservation.status == AgentTokenReservation.Status.EXPIRED
    assert reservation.settled_tokens == 0

    repeated = recover_expired_token_reservations(
        now=NOW + timedelta(hours=2), batch_size=10
    )
    assert repeated.conservative_count == 0
    assert repeated.released_count == 0


def test_usage_reset_rejects_a_stale_ledger_version() -> None:
    admin = _admin()
    endpoint = _endpoint(admin)
    reset_token_usage(
        actor_id=admin.id,
        scope=AgentTokenLedger.Scope.ENDPOINT,
        endpoint_id=endpoint.id,
        reason="确认空 ledger 的初始版本",
        idempotency_key="reset-empty-ledger-001",
        expected_ledger_version=0,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
        now=NOW,
    )

    with pytest.raises(Exception) as stale:
        reset_token_usage(
            actor_id=admin.id,
            scope=AgentTokenLedger.Scope.ENDPOINT,
            endpoint_id=endpoint.id,
            reason="使用过期版本再次重置",
            idempotency_key="reset-empty-ledger-002",
            expected_ledger_version=0,
            trace_code=new_trace_code(),
            client_ip="127.0.0.1",
            now=NOW,
        )
    assert getattr(stale.value, "code", None) == "agents.configuration_conflict.v1"
