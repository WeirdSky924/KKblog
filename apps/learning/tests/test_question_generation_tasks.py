from datetime import timedelta
from uuid import uuid4

import pytest
from django.apps import apps

from apps.accounts.public import active_administrator_id
from apps.agents.providers.http import ProviderTransportError
from apps.core.events.models import OutboxEvent
from apps.core.events.outbox import envelope_from_model
from apps.core.ids import new_ulid
from apps.core.time.clock import FrozenClock
from apps.learning.public import (
    QuestionBankSeriesState,
    delete_knowledge_document,
    execute_question_bank_generation,
    mark_question_bank_generation_final_failed,
)
from apps.learning.services import generation_runtime
from apps.learning.tasks import (
    QUESTION_GENERATION_TASK_NAME,
    generate_question_bank_task,
)
from apps.notifications.public import (
    consume_domain_notification,
    consume_task_final_failure_notification,
)
from apps.operations.models import TaskRun
from apps.operations.public import (
    RetryableTaskError,
    TaskCancelled,
    TaskFinalFailed,
    TaskRetryScheduled,
    current_task_run_id,
    execute_tracked_task,
)

from .test_documents_lifecycle import _account
from .test_question_generation_runtime import (
    NOW,
    _configure_limit,
    _configured_generation_profile,
    _mark_schema_capability,
    _publication_value,
    _request,
)
from .test_review_runtime import _gateway, _openai_response, _scripted_gateway

pytestmark = pytest.mark.django_db(transaction=True)


def _tracked(service, *, moment):
    return execute_tracked_task(
        task_name=QUESTION_GENERATION_TASK_NAME,
        business_object=service.business_object,
        idempotency_key=service.business_object,
        celery_id=str(uuid4()),
        heartbeat_service=service,
        lease_seconds=3_600,
        clock=FrozenClock(moment),
        jitter=lambda _base: 0,
    )


def test_question_generation_task_is_registered_under_stable_name() -> None:
    assert generate_question_bank_task.name == QUESTION_GENERATION_TASK_NAME


def test_celery_entry_executes_tracked_question_generation(
    isolated_media_root,
    monkeypatch,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("generation-celery-owner")
    request, _, _ = _request(
        isolated_media_root,
        owner,
        key="celery",
    )
    gateway, transport = _gateway(_publication_value())
    monkeypatch.setattr(
        "apps.learning.tasks.generation.build_agent_gateway",
        lambda: gateway,
    )

    response = generate_question_bank_task.apply(
        args=(str(request.series_id),),
        task_id=str(uuid4()),
    ).get()

    task_run = TaskRun.objects.get(task_name=QUESTION_GENERATION_TASK_NAME)
    series = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=request.series_id
    )
    assert response["status"] == "succeeded"
    assert response["result_ref"].endswith(":published")
    assert task_run.status == "succeeded" and task_run.attempt == 1
    assert series.state == QuestionBankSeriesState.PUBLISHED
    assert transport.call_count == 1


def test_provider_transient_failures_recover_without_task_level_retry(
    isolated_media_root,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("generation-provider-retry")
    request, _, storage = _request(
        isolated_media_root,
        owner,
        key="provider-retry",
    )
    gateway, transport = _scripted_gateway(
        [
            ProviderTransportError("agents.provider_unavailable.v1", retryable=True),
            ProviderTransportError("agents.provider_unavailable.v1", retryable=True),
            _openai_response(_publication_value()),
        ]
    )

    result = execute_question_bank_generation(
        series_id=request.series_id,
        task_run_id=new_ulid(),
        gateway=gateway,
        renew_lease=lambda: None,
        storage=storage,
        now=NOW,
    )

    series = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=request.series_id
    )
    assert result.state == QuestionBankSeriesState.PUBLISHED
    assert series.attempt_count == 1
    assert transport.call_count == 3


def test_nonretryable_configuration_failure_finalizes_generation_and_notify(
    isolated_media_root,
) -> None:
    administrator, profile = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    endpoint = profile.endpoint
    endpoint.authentication_mode = "SECRET_ALIAS"
    endpoint.secret_alias = "MISSING_GENERATION_KEY"
    endpoint.row_version += 1
    endpoint.save()
    # Capability checks are bound to the endpoint row version.  Recreate the
    # check after this intentional authentication change so the test reaches
    # the missing-secret failure in the generation worker rather than stopping
    # at the preflight capability gate.
    _mark_schema_capability(administrator, endpoint, profile.schema_key)
    owner = _account("generation-final-owner")
    request, _, storage = _request(
        isolated_media_root,
        owner,
        key="final-failure",
    )
    gateway, transport = _gateway(_publication_value())

    def service(business_object, renew_lease):
        run_id = current_task_run_id()
        assert run_id is not None
        execute_question_bank_generation(
            series_id=request.series_id,
            task_run_id=run_id,
            gateway=gateway,
            renew_lease=renew_lease,
            storage=storage,
            now=service.moment,
        )
        return f"question-generation:{request.series_id}:done"

    service.business_object = f"question-generation:{request.series_id}"
    service.moment = NOW
    with pytest.raises(TaskFinalFailed) as final:
        _tracked(service, moment=service.moment)

    terminal = mark_question_bank_generation_final_failed(
        series_id=request.series_id,
        safe_error_code=final.value.error_code,
        completed_at=service.moment,
    )
    series = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=request.series_id
    )
    task_run = TaskRun.objects.get(task_name=QUESTION_GENERATION_TASK_NAME)
    assert terminal.state == QuestionBankSeriesState.GENERATION_FAILED
    assert series.state == QuestionBankSeriesState.GENERATION_FAILED
    assert final.value.error_code == "agents.secret_unavailable.v1"
    assert series.attempt_count == 1
    assert task_run.attempt == 1 and task_run.status == "final_failed"
    assert transport.call_count == 0
    assert series.failure_purge_after == service.moment + timedelta(days=30)

    learning_event = OutboxEvent.objects.get(event_type="learning.generation_failed.v1")
    task_event = OutboxEvent.objects.get(event_type="task.final_failed.v1")
    consume_domain_notification(envelope_from_model(learning_event))
    consume_task_final_failure_notification(
        envelope_from_model(task_event),
        administrator_id_provider=lambda: administrator.id,
    )
    receipt_model = apps.get_model("notifications", "NotificationReceipt")
    assert receipt_model.objects.filter(recipient=owner).count() == 1
    assert receipt_model.objects.filter(recipient=administrator).count() == 1
    assert active_administrator_id() == administrator.id


def test_task_recovers_after_business_commit_without_duplicate_provider_call(
    isolated_media_root,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("generation-post-commit-recovery")
    request, _, storage = _request(
        isolated_media_root,
        owner,
        key="post-commit-recovery",
    )
    gateway, transport = _gateway(_publication_value())
    first = True

    def service(business_object, renew_lease):
        nonlocal first
        run_id = current_task_run_id()
        assert run_id is not None
        result = execute_question_bank_generation(
            series_id=request.series_id,
            task_run_id=run_id,
            gateway=gateway,
            renew_lease=renew_lease,
            storage=storage,
            now=service.moment,
        )
        if first:
            first = False
            raise RetryableTaskError("learning.post_commit_probe.v1")
        return f"question-generation:{result.series_id}:{result.state.casefold()}"

    service.business_object = f"question-generation:{request.series_id}"
    service.moment = NOW
    with pytest.raises(TaskRetryScheduled):
        _tracked(service, moment=NOW)
    service.moment = NOW + timedelta(seconds=60)
    completed = _tracked(service, moment=service.moment)

    series = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=request.series_id
    )
    task_run = TaskRun.objects.get(task_name=QUESTION_GENERATION_TASK_NAME)
    assert completed.result_ref.endswith(":published")
    assert series.state == QuestionBankSeriesState.PUBLISHED
    assert task_run.status == "succeeded" and task_run.attempt == 2
    assert transport.call_count == 1
    assert (
        OutboxEvent.objects.filter(
            event_type="learning.generation_completed.v1",
            aggregate_id=str(series.id),
        ).count()
        == 1
    )


def test_source_delete_race_cancels_late_generation_result(
    isolated_media_root,
    monkeypatch,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("generation-delete-race")
    request, submitted, storage = _request(
        isolated_media_root,
        owner,
        key="delete-race",
    )
    gateway, transport = _gateway(_publication_value())
    original_publish = generation_runtime.publish_question_bank_generation

    def delete_before_publish(**kwargs):
        document = apps.get_model("learning", "KnowledgeDocument").objects.get(
            pk=submitted.document_id
        )
        delete_knowledge_document(
            owner_id=owner.id,
            document_id=document.id,
            expected_version=document.row_version,
            now=NOW + timedelta(minutes=1),
        )
        return original_publish(**kwargs)

    monkeypatch.setattr(
        generation_runtime,
        "publish_question_bank_generation",
        delete_before_publish,
    )

    with pytest.raises(TaskCancelled):
        execute_question_bank_generation(
            series_id=request.series_id,
            task_run_id=new_ulid(),
            gateway=gateway,
            renew_lease=lambda: None,
            storage=storage,
            now=NOW,
        )

    series = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=request.series_id
    )
    assert series.state == QuestionBankSeriesState.GENERATION_FAILED
    assert series.banks.count() == 0
    assert transport.call_count == 1
