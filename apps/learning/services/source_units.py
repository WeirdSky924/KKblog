import re
from dataclasses import dataclass

from apps.learning.contracts import LearningCommandError

_HEADING = re.compile(r"^(#{1,6})[ \t]+([^\n]+?)\s*$")
_ITEM = re.compile(r"^\s*(?:[-+*]|\d+[.)]|[一二三四五六七八九十]+、)\s+")
_MAX_UNIT_BYTES = 48 * 1024
_MAX_UNITS = 4_000


@dataclass(frozen=True, slots=True)
class SourceKnowledgeUnit:
    """A stable, ordered source slice used to anchor generated knowledge."""

    logical_id: str
    ordinal: int
    heading: str
    locator: str
    content: str


def _safe_heading(value: str) -> str:
    return " ".join(value.strip().split())[:300] or "未命名知识点"


def _split_large(content: str) -> tuple[str, ...]:
    if len(content.encode("utf-8")) <= _MAX_UNIT_BYTES:
        return (content,)
    pieces: list[str] = []
    current: list[str] = []
    current_bytes = 0
    for line in content.splitlines(keepends=True):
        size = len(line.encode("utf-8"))
        if current and current_bytes + size > _MAX_UNIT_BYTES:
            pieces.append("".join(current))
            current = []
            current_bytes = 0
        current.append(line)
        current_bytes += size
    if current:
        pieces.append("".join(current))
    return tuple(pieces)


def _heading_units(content: str) -> list[tuple[str, str]]:
    lines = content.splitlines(keepends=True)
    starts = [
        (index, match.group(2))
        for index, line in enumerate(lines)
        if (match := _HEADING.match(line))
    ]
    if not starts:
        return []
    result: list[tuple[str, str]] = []
    for position, (start, heading) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        section = "".join(lines[start:end])
        body = "\n".join(section.splitlines()[1:]).strip()
        # Empty container headings (document title/category labels) are useful
        # navigation but are not atomic knowledge points themselves.
        if not body:
            continue
        result.append((_safe_heading(heading), section))
    return result


def _paragraph_units(content: str) -> list[tuple[str, str]]:
    paragraphs: list[str] = []
    current: list[str] = []
    for line in content.splitlines(keepends=True):
        if current and (not line.strip() or _ITEM.match(line)):
            paragraphs.append("".join(current))
            current = []
        if line.strip():
            current.append(line)
    if current:
        paragraphs.append("".join(current))
    if not paragraphs and content.strip():
        paragraphs = list(_split_large(content))
    return [
        ("未命名知识点", paragraph) for paragraph in paragraphs if paragraph.strip()
    ]


def extract_source_knowledge_units(content: str) -> tuple[SourceKnowledgeUnit, ...]:
    """Detect structure without assuming it, then preserve fine-grained order."""
    if not isinstance(content, str) or not content.strip():
        raise LearningCommandError(
            "learning.source_units_invalid.v1", "知识文档没有可提取的知识内容。"
        )
    candidates = _heading_units(content) or _paragraph_units(content)
    units: list[SourceKnowledgeUnit] = []
    ordinal = 0
    for heading, section in candidates:
        pieces = _split_large(section)
        for part_index, piece in enumerate(pieces, start=1):
            ordinal += 1
            suffix = f"-{part_index:02d}" if len(pieces) > 1 else ""
            logical_id = f"src-{ordinal:04d}{suffix}"
            units.append(
                SourceKnowledgeUnit(
                    logical_id=logical_id,
                    ordinal=ordinal,
                    heading=heading,
                    locator=f"source:{ordinal}",
                    content=piece,
                )
            )
    if not units or len(units) > _MAX_UNITS:
        raise LearningCommandError(
            "learning.source_units_invalid.v1", "知识文档无法安全拆分为知识点。"
        )
    return tuple(units)


def batch_source_knowledge_units(
    units: tuple[SourceKnowledgeUnit, ...],
    *,
    maximum_units: int = 24,
    maximum_bytes: int = _MAX_UNIT_BYTES,
) -> tuple[tuple[SourceKnowledgeUnit, ...], ...]:
    if (
        not isinstance(units, tuple)
        or not units
        or isinstance(maximum_units, bool)
        or not 1 <= maximum_units <= 128
        or isinstance(maximum_bytes, bool)
        or maximum_bytes < 1
    ):
        raise ValueError("Invalid source unit batch configuration")
    batches: list[tuple[SourceKnowledgeUnit, ...]] = []
    current: list[SourceKnowledgeUnit] = []
    current_bytes = 0
    for unit in units:
        size = len(unit.content.encode("utf-8"))
        if current and (
            len(current) >= maximum_units or current_bytes + size > maximum_bytes
        ):
            batches.append(tuple(current))
            current = []
            current_bytes = 0
        current.append(unit)
        current_bytes += size
    if current:
        batches.append(tuple(current))
    return tuple(batches)


__all__ = [
    "SourceKnowledgeUnit",
    "batch_source_knowledge_units",
    "extract_source_knowledge_units",
]
