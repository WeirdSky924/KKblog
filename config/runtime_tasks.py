"""Runtime-only Celery probes; business tasks belong to their owning modules."""

from uuid import UUID

from celery import shared_task

from apps.operations.services.celery import execute_celery_entry


def _smoke_service(probe_id: str) -> str:
    return str(UUID(str(probe_id)))


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
