from collections.abc import Mapping

from apps.core.events import EventDefinition, EventValidationError


def _navigation_changed(payload: Mapping[str, object]) -> None:
    if (
        set(payload) != {"action", "tree_version"}
        or payload["action"]
        not in {"created", "edited", "visibility", "moved", "deleted"}
        or not isinstance(payload["tree_version"], int)
        or isinstance(payload["tree_version"], bool)
        or payload["tree_version"] < 1
    ):
        raise EventValidationError("Navigation event payload shape is invalid")


NAVIGATION_CHANGED = EventDefinition("navigation.changed.v1", _navigation_changed)

__all__ = ["NAVIGATION_CHANGED"]
