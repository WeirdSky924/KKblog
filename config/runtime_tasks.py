"""Runtime-only Celery probes; business tasks belong to their owning modules."""

from uuid import UUID

from celery import shared_task

from apps.core.events import publish_batch
from apps.operations.services.celery import execute_celery_entry
from apps.operations.services.tasks import RetryableTaskError
from config.outbox_transport import build_application_event_transport


def _smoke_service(probe_id: str) -> str:
    return str(UUID(str(probe_id)))


def _publish_outbox_service(batch_id: str) -> str:
    UUID(str(batch_id))
    result = publish_batch(build_application_event_transport())
    if result.failed:
        raise RetryableTaskError("core.outbox_transport_failed.v1")
    return f"outbox:{result.claimed}:{result.published}"


@shared_task(
    bind=True,
    ignore_result=False,
    max_retries=None,
    name="config.runtime_tasks.smoke",
)
def smoke(self, probe_id: str) -> dict[str, str]:
    """Return a safe, broker-backed liveness result for isolated verification."""

    normalized_probe_id = str(UUID(str(probe_id)))
    result = execute_celery_entry(
        self,
        task_name="config.runtime_tasks.smoke",
        business_object=normalized_probe_id,
        idempotency_key=f"runtime-smoke:{normalized_probe_id}",
        service=_smoke_service,
    )
    return {"probe_id": result.result_ref, "status": "ok"}


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name="config.runtime_tasks.publish_outbox",
)
def publish_outbox(self) -> None:
    request_id = getattr(self.request, "id", "")
    execute_celery_entry(
        self,
        task_name="config.runtime_tasks.publish_outbox",
        business_object=request_id,
        idempotency_key=f"outbox:{request_id}",
        service=_publish_outbox_service,
    )
