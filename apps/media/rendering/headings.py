from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Any

_PERSISTED_HEADING_ANCHOR = re.compile(
    r"kaj-h-[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_LEGACY_HEADING_ANCHOR = re.compile(r"kaj-h-legacy-[0-9a-f]{20}")


def is_safe_heading_anchor(value: object, *, allow_legacy: bool = True) -> bool:
    if not isinstance(value, str):
        return False
    return bool(
        _PERSISTED_HEADING_ANCHOR.fullmatch(value)
        or (allow_legacy and _LEGACY_HEADING_ANCHOR.fullmatch(value))
    )


def legacy_heading_anchor(node: dict[str, Any], index: int) -> str:
    serialized = json.dumps(
        [index, node],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = sha256(serialized.encode("utf-8")).hexdigest()[:20]
    return f"kaj-h-legacy-{digest}"


def heading_text(node: dict[str, Any]) -> str:
    parts: list[str] = []

    def visit(value: object) -> None:
        if not isinstance(value, dict):
            return
        if value.get("type") == "text" and isinstance(value.get("text"), str):
            parts.append(value["text"])
        elif value.get("type") == "hardBreak":
            parts.append(" ")
        for child in value.get("content", ()):
            visit(child)

    visit(node)
    return " ".join("".join(parts).split())
