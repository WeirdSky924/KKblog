from importlib import import_module

from .envelope import EventDefinition, EventEnvelope, EventValidationError

__all__ = [
    "ConsumerOutcome",
    "ConsumerResult",
    "EventDefinition",
    "EventEnvelope",
    "EventValidationError",
    "PublishResult",
    "consume_once",
    "enqueue_event",
    "publish_batch",
]

_LAZY_EXPORTS = {
    "ConsumerOutcome": ("apps.core.events.consumer", "ConsumerOutcome"),
    "ConsumerResult": ("apps.core.events.consumer", "ConsumerResult"),
    "PublishResult": ("apps.core.events.publisher", "PublishResult"),
    "consume_once": ("apps.core.events.consumer", "consume_once"),
    "enqueue_event": ("apps.core.events.outbox", "enqueue_event"),
    "publish_batch": ("apps.core.events.publisher", "publish_batch"),
}


def __getattr__(name: str):
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError:
        raise AttributeError(name) from None
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
