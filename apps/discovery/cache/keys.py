from __future__ import annotations

import json
import re
from collections.abc import Mapping
from hashlib import sha256

from apps.core.ids import normalize_ulid

_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9:_-]{1,128}$")


def cache_namespace(value: str) -> str:
    if not isinstance(value, str) or not _SAFE_COMPONENT.fullmatch(value):
        raise ValueError("cache namespace is invalid")
    return value


def _component(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not _SAFE_COMPONENT.fullmatch(value):
        raise ValueError(f"{name} is invalid")
    return value


def list_generation_key(namespace: str) -> str:
    return f"{cache_namespace(namespace)}:cache:g:list"


def article_generation_key(namespace: str, article_id: str) -> str:
    return f"{cache_namespace(namespace)}:cache:g:article:{normalize_ulid(article_id)}"


def article_cache_key(
    namespace: str,
    *,
    article_id: str,
    revision_id: str,
    sanitizer_version: str,
    generation: int,
) -> str:
    if isinstance(generation, bool) or generation < 0:
        raise ValueError("cache generation is invalid")
    return (
        f"{cache_namespace(namespace)}:cache:article:{normalize_ulid(article_id)}:"
        f"{normalize_ulid(revision_id)}:"
        f"{_component(sanitizer_version, name='sanitizer version')}:g{generation}"
    )


def list_cache_key(namespace: str, *, query_hash: str, generation: int) -> str:
    if isinstance(generation, bool) or generation < 0:
        raise ValueError("cache generation is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", query_hash):
        raise ValueError("query hash is invalid")
    return f"{cache_namespace(namespace)}:cache:list:{query_hash}:g{generation}"


def _json_value(value):
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_value(item) for item in value]
    return str(value)


def list_query_hash(kind: str, parameters: Mapping[str, object]) -> str:
    normalized_kind = _component(kind, name="query kind")
    payload = json.dumps(
        {"version": 1, "kind": normalized_kind, "parameters": _json_value(parameters)},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(payload).hexdigest()
