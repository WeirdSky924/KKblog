from collections.abc import Mapping
from dataclasses import dataclass

_MAX_FEEDBACK_COUNT = 1_000_000_000


@dataclass(frozen=True, slots=True)
class LearningBatchFeedback:
    total: int
    succeeded: int
    failed: int
    error: str = ""


def feedback_count(query: Mapping[str, object], key: str) -> int | None:
    """Parse a redirect feedback count without turning missing data into zero."""
    raw = query.get(key)
    if raw is None or isinstance(raw, bool):
        return None
    text = str(raw).strip()
    if not text or len(text) > 10 or text.startswith(("+", "-")):
        return None
    try:
        value = int(text)
    except (TypeError, ValueError):
        return None
    if not 0 <= value <= _MAX_FEEDBACK_COUNT:
        return None
    return value


def learning_batch_feedback(
    query: Mapping[str, object], *, saved: str
) -> LearningBatchFeedback | None:
    if saved != "batch":
        return None
    total = feedback_count(query, "total")
    succeeded = feedback_count(query, "succeeded")
    failed = feedback_count(query, "failed")
    if total is None or succeeded is None or failed is None:
        return None
    if succeeded + failed != total:
        return None
    raw_error = query.get("error") if failed else None
    error = str(raw_error).strip()[:500] if raw_error else ""
    return LearningBatchFeedback(
        total=total,
        succeeded=succeeded,
        failed=failed,
        error=error,
    )


__all__ = [
    "LearningBatchFeedback",
    "feedback_count",
    "learning_batch_feedback",
]
