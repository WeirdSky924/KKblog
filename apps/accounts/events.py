from collections.abc import Mapping

from apps.accounts.deletion import AuthorArticleDecision
from apps.core.events import EventDefinition, EventValidationError
from apps.core.ids import is_ulid


def _exact(payload: Mapping[str, object], fields: set[str]) -> None:
    if set(payload) != fields:
        raise EventValidationError("Account event payload shape is invalid")


def _author_role_changed(payload: Mapping[str, object]) -> None:
    _exact(payload, {"enabled"})
    if not isinstance(payload["enabled"], bool):
        raise EventValidationError("Account event payload shape is invalid")


def _account_status_changed(payload: Mapping[str, object]) -> None:
    _exact(payload, set())


def _account_registered(payload: Mapping[str, object]) -> None:
    _exact(payload, set())


def _author_permission_requested(payload: Mapping[str, object]) -> None:
    _exact(payload, set())


def _account_deleted(payload: Mapping[str, object]) -> None:
    _exact(
        payload,
        {
            "deletion_id",
            "was_author",
            "author_disposition",
            "disposition_id",
            "article_count",
        },
    )
    try:
        decision = AuthorArticleDecision(payload["author_disposition"])
    except (TypeError, ValueError):
        raise EventValidationError("Account event payload shape is invalid") from None
    article_count = payload["article_count"]
    disposition_id = payload["disposition_id"]
    was_author = payload["was_author"]
    if (
        not isinstance(payload["deletion_id"], str)
        or not is_ulid(payload["deletion_id"])
        or not isinstance(was_author, bool)
        or isinstance(article_count, bool)
        or not isinstance(article_count, int)
        or not 0 <= article_count <= 1_000_000
        or not isinstance(disposition_id, str)
        or not is_ulid(disposition_id)
        or (decision == AuthorArticleDecision.NO_ARTICLES and article_count != 0)
        or (
            decision
            in {
                AuthorArticleDecision.DELETE_ALL,
                AuthorArticleDecision.EXPORT_THEN_DELETE,
            }
            and article_count == 0
        )
    ):
        raise EventValidationError("Account event payload shape is invalid")


AUTHOR_ROLE_CHANGED = EventDefinition(
    "account.author_role_changed.v1", _author_role_changed
)
ACCOUNT_REGISTERED = EventDefinition("account.registered.v1", _account_registered)
AUTHOR_PERMISSION_REQUESTED = EventDefinition(
    "account.author_permission_requested.v1", _author_permission_requested
)
ACCOUNT_DISABLED = EventDefinition("account.disabled.v1", _account_status_changed)
ACCOUNT_ENABLED = EventDefinition("account.enabled.v1", _account_status_changed)
ACCOUNT_DELETED = EventDefinition("account.deleted.v1", _account_deleted)

ACCOUNT_EVENT_DEFINITIONS = {
    item.event_type: item
    for item in (
        AUTHOR_ROLE_CHANGED,
        ACCOUNT_REGISTERED,
        AUTHOR_PERMISSION_REQUESTED,
        ACCOUNT_DISABLED,
        ACCOUNT_ENABLED,
        ACCOUNT_DELETED,
    )
}
