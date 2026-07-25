from .account_events import (
    consume_account_deleted,
    consume_author_role_changed,
    register_account_event_templates,
)
from .domain_events import consume_domain_notification

__all__ = [
    "consume_domain_notification",
    "consume_author_role_changed",
    "consume_account_deleted",
    "register_account_event_templates",
]
