"""Django model discovery shim; ownership remains in ``apps.core.events``."""

from apps.core.events.models import EventConsumerRecord, OutboxEvent

__all__ = ["EventConsumerRecord", "OutboxEvent"]
