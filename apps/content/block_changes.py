from __future__ import annotations

import json
from bisect import bisect_left
from collections import defaultdict, deque
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from apps.media.public import RenderingError, normalize_tiptap_document

from .snapshots import ContentFormat


@dataclass(frozen=True, slots=True)
class BlockChangeSummary:
    available: bool
    before_blocks: int
    after_blocks: int
    added_blocks: int
    deleted_blocks: int
    moved_blocks: int
    type_changed_blocks: int
    content_changed_blocks: int

    @property
    def changed(self) -> bool:
        return any(
            (
                self.added_blocks,
                self.deleted_blocks,
                self.moved_blocks,
                self.type_changed_blocks,
                self.content_changed_blocks,
            )
        )


@dataclass(frozen=True, slots=True)
class _BlockSignature:
    kind: str
    exact: str
    semantic: str


_UNAVAILABLE = BlockChangeSummary(False, 0, 0, 0, 0, 0, 0, 0)


def _fingerprint(value: object) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(serialized).hexdigest()


def _signature(block: dict[str, Any]) -> _BlockSignature:
    content = block.get("content")
    semantic = (
        {"content": content}
        if content is not None
        else {"attrs": block.get("attrs", {})}
    )
    return _BlockSignature(
        kind=block["type"],
        exact=_fingerprint(block),
        semantic=_fingerprint(semantic),
    )


def _normalized_blocks(
    *,
    content_format: ContentFormat | str,
    body: str | dict[str, Any],
    schema_version: int | None,
) -> tuple[_BlockSignature, ...] | None:
    try:
        if ContentFormat(content_format) != ContentFormat.TIPTAP_JSON:
            return None
    except (TypeError, ValueError):
        return None
    if not isinstance(body, dict) or schema_version is None:
        return None
    try:
        document = normalize_tiptap_document(
            body,
            schema_version=schema_version,
        ).document
    except (RenderingError, TypeError, ValueError, RecursionError):
        return None
    return tuple(_signature(block) for block in document.get("content", ()))


def _longest_increasing_subsequence_size(values: list[int]) -> int:
    tails: list[int] = []
    for value in values:
        position = bisect_left(tails, value)
        if position == len(tails):
            tails.append(value)
        else:
            tails[position] = value
    return len(tails)


def _exact_pairs(
    before: tuple[_BlockSignature, ...],
    after: tuple[_BlockSignature, ...],
) -> tuple[list[tuple[int, int]], set[int], set[int]]:
    available: dict[str, deque[int]] = defaultdict(deque)
    for index, signature in enumerate(before):
        available[signature.exact].append(index)
    pairs: list[tuple[int, int]] = []
    unmatched_before = set(range(len(before)))
    unmatched_after = set(range(len(after)))
    for after_index, signature in enumerate(after):
        candidates = available.get(signature.exact)
        if not candidates:
            continue
        before_index = candidates.popleft()
        pairs.append((before_index, after_index))
        unmatched_before.remove(before_index)
        unmatched_after.remove(after_index)
    return pairs, unmatched_before, unmatched_after


def _type_change_pairs(
    before: tuple[_BlockSignature, ...],
    after: tuple[_BlockSignature, ...],
    unmatched_before: set[int],
    unmatched_after: set[int],
) -> list[tuple[int, int]]:
    available: dict[str, dict[str, deque[int]]] = defaultdict(
        lambda: defaultdict(deque)
    )
    for index in sorted(unmatched_before):
        signature = before[index]
        available[signature.semantic][signature.kind].append(index)
    pairs: list[tuple[int, int]] = []
    for after_index in sorted(tuple(unmatched_after)):
        signature = after[after_index]
        candidates = available.get(signature.semantic, {})
        choices = [
            (indices[0], kind)
            for kind, indices in candidates.items()
            if kind != signature.kind and indices
        ]
        if not choices:
            continue
        before_index, kind = min(choices)
        candidates[kind].popleft()
        pairs.append((before_index, after_index))
        unmatched_before.remove(before_index)
        unmatched_after.remove(after_index)
    return pairs


def _content_change_count(
    before: tuple[_BlockSignature, ...],
    after: tuple[_BlockSignature, ...],
    unmatched_before: set[int],
    unmatched_after: set[int],
) -> int:
    available: dict[str, deque[int]] = defaultdict(deque)
    for index in sorted(unmatched_before):
        available[before[index].kind].append(index)
    changed = 0
    for after_index in sorted(tuple(unmatched_after)):
        candidates = available.get(after[after_index].kind)
        if not candidates:
            continue
        before_index = candidates.popleft()
        unmatched_before.remove(before_index)
        unmatched_after.remove(after_index)
        changed += 1
    return changed


def project_article_block_changes(
    *,
    before_content_format: ContentFormat | str,
    before_body: str | dict[str, Any],
    before_schema_version: int | None,
    after_content_format: ContentFormat | str,
    after_body: str | dict[str, Any],
    after_schema_version: int | None,
) -> BlockChangeSummary:
    before = _normalized_blocks(
        content_format=before_content_format,
        body=before_body,
        schema_version=before_schema_version,
    )
    after = _normalized_blocks(
        content_format=after_content_format,
        body=after_body,
        schema_version=after_schema_version,
    )
    if before is None or after is None:
        return _UNAVAILABLE

    pairs, unmatched_before, unmatched_after = _exact_pairs(before, after)
    type_pairs = _type_change_pairs(
        before,
        after,
        unmatched_before,
        unmatched_after,
    )
    pairs.extend(type_pairs)
    content_changed = _content_change_count(
        before,
        after,
        unmatched_before,
        unmatched_after,
    )
    target_order = [target for _, target in sorted(pairs)]
    moved = len(target_order) - _longest_increasing_subsequence_size(target_order)
    return BlockChangeSummary(
        available=True,
        before_blocks=len(before),
        after_blocks=len(after),
        added_blocks=len(unmatched_after),
        deleted_blocks=len(unmatched_before),
        moved_blocks=moved,
        type_changed_blocks=len(type_pairs),
        content_changed_blocks=content_changed,
    )


__all__ = ["BlockChangeSummary", "project_article_block_changes"]
