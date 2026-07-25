import re
from collections.abc import Callable
from uuid import UUID

from apps.core.events import EventEnvelope, consume_once
from apps.core.ids import is_ulid
from apps.core.time.clock import Clock
from apps.notifications.services.delivery import (
    NotificationRejected,
    deliver_notification,
)
from apps.notifications.services.recipients import (
    existing_notification_recipient_ids,
)

CONSUMER_NAME = "notifications.task-final-failure.v1"
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9:_.-]{0,254}\Z")
_SAFE_CODE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*\Z")

AdministratorIdProvider = Callable[[], UUID | None]


def _handle(
    envelope: EventEnvelope,
    *,
    administrator_id_provider: AdministratorIdProvider,
) -> None:
    required = {
        "task_name",
        "business_object",
        "idempotency_key",
        "attempt",
        "error_code",
    }
    if (
        not isinstance(envelope, EventEnvelope)
        or envelope.event_type != "task.final_failed.v1"
        or envelope.schema_version != 1
        or envelope.aggregate_type != "task_run"
        or not is_ulid(envelope.aggregate_id)
        or set(envelope.payload) != required
    ):
        raise NotificationRejected("Invalid task final failure event")
    for field in ("task_name", "business_object", "idempotency_key"):
        if not isinstance(envelope.payload[field], str) or not _SAFE_ID.fullmatch(
            envelope.payload[field]
        ):
            raise NotificationRejected("Invalid task final failure event")
    attempt = envelope.payload["attempt"]
    error_code = envelope.payload["error_code"]
    if (
        isinstance(attempt, bool)
        or attempt != 3
        or not isinstance(error_code, str)
        or not _SAFE_CODE.fullmatch(error_code)
    ):
        raise NotificationRejected("Invalid task final failure event")
    if not callable(administrator_id_provider):
        raise TypeError("Administrator ID provider must be callable")
    administrator_id = administrator_id_provider()
    if not isinstance(administrator_id, UUID):
        raise NotificationRejected("Active administrator is unavailable")
    recipients = existing_notification_recipient_ids((administrator_id,))
    if recipients != (administrator_id,):
        raise NotificationRejected("Active administrator is unavailable")
    deliver_notification(
        template_key="task.final_failed.v1",
        recipient_ids=recipients,
        target_id=envelope.aggregate_id,
        payload={
            "task_name": envelope.payload["task_name"],
            "attempt": attempt,
            "error_code": error_code,
        },
        dedupe_key=f"task-final:{envelope.aggregate_id}",
    )


def consume_task_final_failure_notification(
    envelope: EventEnvelope,
    *,
    administrator_id_provider: AdministratorIdProvider,
    lease_seconds: int = 60,
    retry_delay_seconds: int = 60,
    clock: Clock | None = None,
):
    return consume_once(
        envelope,
        CONSUMER_NAME,
        lambda item: _handle(
            item,
            administrator_id_provider=administrator_id_provider,
        ),
        lease_seconds=lease_seconds,
        retry_delay_seconds=retry_delay_seconds,
        clock=clock,
    )
