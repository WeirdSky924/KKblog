import logging
import math
import re

RICH_TEXT_RENDER_BUDGET_MS = 250.0

_CONTENT_FORMATS = frozenset({"MARKDOWN", "TIPTAP_JSON"})
_MODES = frozenset({"export", "reader", "strict", "summary"})
_OUTCOMES = frozenset({"error", "rejected", "success"})
_ERROR_CODE = re.compile(r"(?:-|[a-z][a-z0-9_.-]{0,79})")

logger = logging.getLogger("kaj.performance.rich_text")


def _choice(value: object, allowed: frozenset[str], label: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"Invalid rich-text {label}")
    return value


def _count(value: object, label: str, *, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"Invalid rich-text {label}")
    return value


def _duration(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("Invalid rich-text duration")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0 <= normalized <= 600_000:
        raise ValueError("Invalid rich-text duration")
    return normalized


def record_rich_text_render_metric(
    *,
    content_format: str,
    mode: str,
    schema_version: int | None,
    source_bytes: int,
    node_count: int,
    max_depth: int,
    table_cells: int,
    duration_ms: float,
    outcome: str,
    error_code: str,
) -> None:
    normalized_format = _choice(content_format, _CONTENT_FORMATS, "format")
    normalized_mode = _choice(mode, _MODES, "mode")
    normalized_outcome = _choice(outcome, _OUTCOMES, "outcome")
    if schema_version is not None and (
        type(schema_version) is not int or schema_version not in {1, 2}
    ):
        raise ValueError("Invalid rich-text schema version")
    normalized_source_bytes = _count(
        source_bytes, "source byte count", maximum=64 * 1024 * 1024
    )
    normalized_nodes = _count(node_count, "node count", maximum=1_000_000)
    normalized_depth = _count(max_depth, "depth", maximum=10_000)
    normalized_cells = _count(table_cells, "table cell count", maximum=1_000_000)
    normalized_duration = _duration(duration_ms)
    if not isinstance(error_code, str) or not _ERROR_CODE.fullmatch(error_code):
        raise ValueError("Invalid rich-text error code")

    level = (
        logging.WARNING
        if normalized_outcome != "success"
        or normalized_duration > RICH_TEXT_RENDER_BUDGET_MS
        else logging.INFO
    )
    logger.log(
        level,
        "Rich text render format=%s mode=%s schema=%s source_bytes=%s "
        "nodes=%s depth=%s table_cells=%s duration_ms=%.3f budget_ms=%.3f "
        "outcome=%s code=%s",
        normalized_format,
        normalized_mode,
        schema_version if schema_version is not None else "-",
        normalized_source_bytes,
        normalized_nodes,
        normalized_depth,
        normalized_cells,
        normalized_duration,
        RICH_TEXT_RENDER_BUDGET_MS,
        normalized_outcome,
        error_code,
    )


__all__ = ["RICH_TEXT_RENDER_BUDGET_MS", "record_rich_text_render_metric"]
