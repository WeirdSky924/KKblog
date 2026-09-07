from datetime import timedelta
from uuid import uuid4

import pytest
from django.apps import apps

from apps.accounts.public import active_administrator_id
from apps.core.events.models import OutboxEvent
from apps.core.events.outbox import envelope_from_model
from apps.core.ids import new_ulid
from apps.core.time.clock import FrozenClock
from apps.learning.public import (
    KnowledgeDocumentState,
    LearningModelRunKind,
    delete_knowledge_document,
    execute_knowledge_review,
    mark_knowledge_review_final_failed,
    release_learning_model_run,
    reserve_learning_model_run,
)
from apps.learning.services import review_runtime
from apps.learning.tasks import REVIEW_DOCUMENT_TASK_NAME, review_document_task
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

from .test_review_runtime import (
    NOW,
    _account,
    _configured_profile,
    _gateway,
    _submitted,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _tracked(service, *, moment):
    return execute_tracked_task(
        task_name=REVIEW_DOCUMENT_TASK_NAME,
        business_object=service.business_object,
        idempotency_key=service.business_object,
        celery_id=str(uuid4()),
        heartbeat_service=service,
        lease_seconds=3_600,
        clock=FrozenClock(moment),
        jitter=lambda _base: 0,
    )


def test_review_task_is_registered_under_stable_name() -> None:
    assert review_document_task.name == REVIEW_DOCUMENT_TASK_NAME


def test_celery_entry_executes_tracked_review(
    isolated_media_root,
    monkeypatch,
) -> None:
    _configured_profile()
    owner = _account("review-celery-owner", author=True)
    submitted, _, _ = _submitted(isolated_media_root, owner)
    gateway, transport = _gateway(
        {
            "verdict": "APPROVED",
            "reason_code": "knowledge_valid",
            "summary": "Celery 审核成功。",
            "risk_categories": [],
        }
    )
    monkeypatch.setattr(
        "apps.learning.tasks.review.build_agent_gateway",
        lambda: gateway,
    )

    response = review_document_task.apply(
        args=(str(submitted.review_run_id),),
        task_id=str(uuid4()),
    ).get()
    task_run = TaskRun.objects.get(task_name=REVIEW_DOCUMENT_TASK_NAME)
    document = review_runtime.KnowledgeDocument.objects.get(pk=submitted.document_id)
    assert response["status"] == "succeeded"
    assert response["result_ref"].endswith(":approved")
    assert task_run.status == "succeeded" and task_run.attempt == 1
    assert document.state == KnowledgeDocumentState.APPROVED
    assert transport.call_count == 1


def test_stale_endpoint_capability_fails_review_immediately(
    isolated_media_root,
):
    profile = _configured_profile()
    owner = _account("review-stale-capability", author=True)
    submitted, _, _ = _submitted(isolated_media_root, owner)

    # Editing any endpoint runtime setting invalidates the prior strict schema
    # probe.  The worker must surface that configuration problem immediately;
    # waiting for the one-hour review lease would strand the document.
    endpoint = profile.endpoint
    endpoint.row_version += 1
    endpoint.save(update_fields=("row_version", "updated_at"))

    with pytest.raises(RuntimeError) as failed:
        review_document_task.apply(
            args=(str(submitted.review_run_id),),
            task_id=str(uuid4()),
        ).get()

    # Celery's eager trace serializes the task exception back as RuntimeError;
    # the durable TaskRun and review records remain the source of truth.
    assert str(failed.value) == "agents.profile_capability_unverified.v1"
    document = review_runtime.KnowledgeDocument.objects.get(pk=submitted.document_id)
    run = review_runtime.KnowledgeReviewRun.objects.get(pk=submitted.review_run_id)
    task_run = TaskRun.objects.get(task_name=REVIEW_DOCUMENT_TASK_NAME)
    assert document.state == KnowledgeDocumentState.REVIEW_FAILED
    assert run.state == "FAILED"
    assert run.last_error_code == "agents.profile_capability_unverified.v1"
    assert task_run.status == "final_failed"


def test_three_agent_configuration_failures_finalize_review_and_notify(
    isolated_media_root,
) -> None:
    administrator = _account("review-final-admin", administrator=True)
    owner = _account("review-final-owner", author=True)
    submitted, _, storage = _submitted(isolated_media_root, owner)
    gateway, transport = _gateway(
        {
            "verdict": "APPROVED",
            "reason_code": "knowledge_valid",
            "summary": "不会被调用。",
            "risk_categories": [],
        }
    )

    def service(business_object, renew_lease):
        run_id = current_task_run_id()
        assert run_id is not None
        execute_knowledge_review(
            review_run_id=submitted.review_run_id,
            task_run_id=run_id,
            gateway=gateway,
            renew_lease=renew_lease,
            storage=storage,
            now=service.moment,
        )
        return f"knowledge-review:{submitted.review_run_id}:done"

    service.business_object = f"knowledge-review:{submitted.review_run_id}"
    for moment, countdown in (
        (NOW, 60),
        (NOW + timedelta(seconds=60), 300),
    ):
        service.moment = moment
        with pytest.raises(TaskRetryScheduled) as retry:
            _tracked(service, moment=moment)
        assert retry.value.countdown == countdown
    service.moment = NOW + timedelta(seconds=360)
    with pytest.raises(TaskFinalFailed) as final:
        _tracked(service, moment=service.moment)

    terminal = mark_knowledge_review_final_failed(
        review_run_id=submitted.review_run_id,
        safe_error_code=final.value.error_code,
        completed_at=service.moment,
    )
    document_model = review_runtime.KnowledgeDocument
    run_model = review_runtime.KnowledgeReviewRun
    document = document_model.objects.get(pk=submitted.document_id)
    run = run_model.objects.get(pk=submitted.review_run_id)
    task_run = TaskRun.objects.get(task_name=REVIEW_DOCUMENT_TASK_NAME)
    assert terminal.document_state == KnowledgeDocumentState.REVIEW_FAILED
    assert document.state == KnowledgeDocumentState.REVIEW_FAILED
    assert run.state == "FAILED" and run.attempt_count == 3
    assert task_run.attempt == 3 and task_run.status == "final_failed"
    assert transport.call_count == 0
    assert document.failure_purge_after == service.moment + timedelta(days=30)

    learning_event = OutboxEvent.objects.get(event_type="learning.review_failed.v1")
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


def test_business_concurrency_blocks_before_provider_call(isolated_media_root) -> None:
    _configured_profile()
    owner = _account("review-business-quota", author=True)
    submitted, _, storage = _submitted(isolated_media_root, owner)
    blocker_ref = str(uuid4())
    blocker = reserve_learning_model_run(
        account_id=owner.id,
        kind=LearningModelRunKind.GENERATION,
        owner_ref=blocker_ref,
        idempotency_key=f"review-blocker:{blocker_ref}",
        lease_expires_at=NOW + timedelta(hours=1),
        now=NOW,
    )
    gateway, transport = _gateway(
        {
            "verdict": "APPROVED",
            "reason_code": "knowledge_valid",
            "summary": "不应调用 Provider。",
            "risk_categories": [],
        }
    )

    with pytest.raises(RetryableTaskError) as blocked:
        execute_knowledge_review(
            review_run_id=submitted.review_run_id,
            task_run_id=new_ulid(),
            gateway=gateway,
            renew_lease=lambda: None,
            storage=storage,
            now=NOW,
        )
    assert blocked.value.error_code == "learning.concurrent_quota_exhausted.v1"
    assert transport.call_count == 0
    release_learning_model_run(reservation_id=blocker.reservation_id)


def test_delete_race_cancels_late_gateway_result(
    isolated_media_root, monkeypatch
) -> None:
    _configured_profile()
    owner = _account("review-delete-race", author=True)
    submitted, _, storage = _submitted(isolated_media_root, owner)
    gateway, transport = _gateway(
        {
            "verdict": "APPROVED",
            "reason_code": "knowledge_valid",
            "summary": "稍后被删除竞态拦截。",
            "risk_categories": [],
        }
    )
    original_complete = review_runtime.complete_knowledge_review

    def delete_before_complete(**kwargs):
        delete_knowledge_document(
            owner_id=owner.id,
            document_id=submitted.document_id,
            expected_version=kwargs["expected_document_version"],
            now=NOW + timedelta(seconds=1),
        )
        return original_complete(**kwargs)

    monkeypatch.setattr(
        review_runtime,
        "complete_knowledge_review",
        delete_before_complete,
    )
    with pytest.raises(TaskCancelled):
        execute_knowledge_review(
            review_run_id=submitted.review_run_id,
            task_run_id=new_ulid(),
            gateway=gateway,
            renew_lease=lambda: None,
            storage=storage,
            now=NOW,
        )
    document = review_runtime.KnowledgeDocument.objects.get(pk=submitted.document_id)
    assert document.state == KnowledgeDocumentState.DELETE_PENDING
    assert transport.call_count == 1
