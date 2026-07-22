from .account_events import (
    consume_account_deleted,
    consume_author_role_changed,
    register_account_event_templates,
)

__all__ = [
    "consume_author_role_changed",
    "consume_account_deleted",
    "register_account_event_templates",
]
