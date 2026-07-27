from __future__ import annotations

from datetime import date, datetime

import yaml
from yaml.tokens import AliasToken, AnchorToken, TagToken

_MAX_FRONT_MATTER_BYTES = 64 * 1024
_ALLOWED_FIELDS = frozenset(
    {
        "id",
        "title",
        "visibility",
        "section",
        "tags",
        "cover",
        "summary",
        "summary_mode",
        "status",
        "scheduled_for",
        "published_at",
        "comments_enabled",
        "comments_view_login",
        "comments_post_login",
    }
)
_SCALAR_TYPES = (str, int, float, bool, type(None))


class FrontMatterError(ValueError):
    pass


def _validate_value(value: object) -> bool:
    if isinstance(value, (date, datetime)):
        return False
    if isinstance(value, _SCALAR_TYPES):
        return True
    return isinstance(value, list) and all(
        isinstance(item, _SCALAR_TYPES) and not isinstance(item, (date, datetime))
        for item in value
    )


def _load_metadata(source: str) -> dict[str, object]:
    if len(source.encode("utf-8")) > _MAX_FRONT_MATTER_BYTES:
        raise FrontMatterError("Front Matter exceeds safety limit")
    try:
        if any(
            isinstance(token, (AliasToken, AnchorToken, TagToken))
            for token in yaml.scan(source, Loader=yaml.SafeLoader)
        ):
            raise FrontMatterError("Front Matter aliases and tags are not allowed")
        loaded = yaml.safe_load(source)
    except FrontMatterError:
        raise
    except yaml.YAMLError:
        raise FrontMatterError("Front Matter is invalid") from None
    if loaded is None:
        return {}
    if not isinstance(loaded, dict) or any(
        not isinstance(key, str)
        or key not in _ALLOWED_FIELDS
        or not _validate_value(value)
        for key, value in loaded.items()
    ):
        raise FrontMatterError("Front Matter contains unsupported fields or values")
    return loaded


def split_front_matter(source: str) -> tuple[dict[str, object], str]:
    if not isinstance(source, str):
        raise FrontMatterError("Markdown source must be text")
    normalized = source.removeprefix("\ufeff")
    lines = normalized.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, normalized
    closing = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() in {"---", "..."}
        ),
        None,
    )
    if closing is None:
        raise FrontMatterError("Front Matter is not terminated")
    metadata = _load_metadata("".join(lines[1:closing]))
    return metadata, "".join(lines[closing + 1 :])
