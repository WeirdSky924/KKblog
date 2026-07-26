from collections.abc import Callable
from uuid import UUID

from apps.core.events import EventEnvelope, consume_once
from apps.core.time.clock import Clock
from apps.notifications.services.delivery import (
    NotificationRejected,
    deliver_notification,
)
from apps.notifications.services.recipients import (
    existing_notification_recipient_ids,
)

CONSUMER_NAME = "notifications.operational-state.v1"
_EVENT_CONTRACTS = {
    "capacity.threshold_changed.v1": (
        "capacity_state",
        frozenset({"media_disk"}),
        frozenset({"unknown", "normal", "warn", "no_image", "read_only"}),
    ),
    "service.health_changed.v1": (
        "service_health",
        frozenset({"application"}),
        frozenset({"unknown", "healthy", "unavailable"}),
    ),
}

AdministratorIdProvider = Callable[[], UUID | None]


def _administrator_recipient(
    provider: AdministratorIdProvider,
) -> tuple[UUID, ...]:
    if not callable(provider):
        raise TypeError("Administrator ID provider must be callable")
    administrator_id = provider()
    if not isinstance(administrator_id, UUID):
        raise NotificationRejected("Active administrator is unavailable")
    recipients = existing_notification_recipient_ids((administrator_id,))
    if recipients != (administrator_id,):
        raise NotificationRejected("Active administrator is unavailable")
    return recipients


def _handle(
    envelope: EventEnvelope,
    *,
    administrator_id_provider: AdministratorIdProvider,
) -> None:
    if not isinstance(envelope, EventEnvelope) or envelope.schema_version != 1:
        raise NotificationRejected("Invalid operational state event")
    contract = _EVENT_CONTRACTS.get(envelope.event_type)
    if contract is None:
        raise NotificationRejected("Invalid operational state event")
    aggregate_type, sources, states = contract
    required = {"source_key", "previous_state", "current_state"}
    source_key = envelope.payload.get("source_key")
    previous_state = envelope.payload.get("previous_state")
    current_state = envelope.payload.get("current_state")
    if (
        envelope.aggregate_type != aggregate_type
        or envelope.aggregate_id not in sources
        or set(envelope.payload) != required
        or source_key != envelope.aggregate_id
        or previous_state not in states
        or current_state not in states - {"unknown"}
        or previous_state == current_state
    ):
        raise NotificationRejected("Invalid operational state event")
    deliver_notification(
        template_key=envelope.event_type,
        recipient_ids=_administrator_recipient(administrator_id_provider),
        target_id=envelope.aggregate_id,
        payload={
            "source_key": source_key,
            "previous_state": previous_state,
            "current_state": current_state,
        },
        dedupe_key=f"operational-state:{envelope.event_id}",
    )


def consume_operational_state_notification(
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
