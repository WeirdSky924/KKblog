from collections.abc import Mapping
from datetime import date
from uuid import UUID

from apps.core.events import EventDefinition, EventValidationError
from apps.core.ids import is_ulid


def _import_title_warning(payload: Mapping[str, object]) -> None:
    if set(payload) != {"job_id", "item_id", "recipient_id"}:
        raise EventValidationError("Import warning event payload shape is invalid")
    try:
        recipient = UUID(str(payload["recipient_id"]))
    except (TypeError, ValueError):
        raise EventValidationError(
            "Import warning event payload shape is invalid"
        ) from None
    if (
        not isinstance(payload["job_id"], str)
        or not is_ulid(payload["job_id"])
        or not isinstance(payload["item_id"], str)
        or not is_ulid(payload["item_id"])
        or not isinstance(recipient, UUID)
    ):
        raise EventValidationError("Import warning event payload shape is invalid")


IMPORT_TITLE_WARNING = EventDefinition(
    "exchange.import_title_warning.v1",
    _import_title_warning,
)


def _export_recipient(payload: Mapping[str, object], *, dated: bool) -> None:
    expected = {"recipient_id", "export_date"} if dated else {"recipient_id"}
    if set(payload) != expected:
        raise EventValidationError("Export notification payload shape is invalid")
    try:
        UUID(str(payload["recipient_id"]))
        parsed = (
            date.fromisoformat(payload["export_date"])
            if dated and isinstance(payload["export_date"], str)
            else None
        )
    except (TypeError, ValueError):
        raise EventValidationError(
            "Export notification payload shape is invalid"
        ) from None
    if dated and (parsed is None or parsed.isoformat() != payload["export_date"]):
        raise EventValidationError("Export notification payload shape is invalid")


EXPORT_COMPLETED = EventDefinition(
    "exchange.export_completed.v1",
    lambda payload: _export_recipient(payload, dated=False),
)
EXPORT_AUTHOR_CONTENT = EventDefinition(
    "exchange.export_author_content.v1",
    lambda payload: _export_recipient(payload, dated=True),
)
