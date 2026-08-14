from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction

from ..checks.adapters import registered_adapters
from ..models import OpportunitySource, OpportunitySourceHost
from ..validators import (
    normalize_adapter_key,
    normalize_hostname,
    normalize_opportunity_url,
    normalized_text,
    optional_text,
)

SCHEMA = "kaj.opportunity-source-config.v1"
MAX_SOURCES = 500
MAX_ADAPTER_CONFIG_BYTES = 32_768
_SOURCE_KEYS = frozenset(
    {
        "id",
        "company_name",
        "source_type",
        "official_url",
        "note",
        "adapter_key",
        "adapter_config",
        "enabled",
        "respect_robots_txt",
        "request_interval_seconds",
        "max_pages",
        "max_opportunities",
        "max_duration_seconds",
        "allowed_hosts",
    }
)
_SENSITIVE_CONFIG_KEY = re.compile(
    r"(?:password|secret|token|credential|cookie|authorization|api[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)


class SourceManifestError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SourceManifestRow:
    id: UUID
    company_name: str
    source_type: str
    official_url: str
    note: str
    adapter_key: str
    adapter_config: dict[str, Any]
    enabled: bool
    respect_robots_txt: bool
    request_interval_seconds: int
    max_pages: int
    max_opportunities: int
    max_duration_seconds: int
    allowed_hosts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceImportResult:
    created: int
    updated: int


def _fail(message: str) -> SourceManifestError:
    return SourceManifestError(message)


def _bounded_int(value: object, *, minimum: int, maximum: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise _fail(f"{field} is outside the allowed range")
    return value


def _safe_adapter_config(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise _fail("adapter_config must be a JSON object")
    for key in value:
        if not key or len(key) > 80 or _SENSITIVE_CONFIG_KEY.search(key):
            raise _fail("adapter_config contains an unsafe key")
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise _fail("adapter_config must contain finite JSON values") from None
    if len(encoded) > MAX_ADAPTER_CONFIG_BYTES:
        raise _fail("adapter_config is too large")
    return value


def _parse_row(raw: object) -> SourceManifestRow:
    if not isinstance(raw, dict) or set(raw) != _SOURCE_KEYS:
        raise _fail("source fields do not match the source-only schema")
    try:
        identity = UUID(str(raw["id"]))
        company = normalized_text(
            raw["company_name"], maximum=120, field="company_name"
        )
        url, url_host = normalize_opportunity_url(raw["official_url"])
        note = optional_text(raw["note"], maximum=500, field="note")
        adapter_key = normalize_adapter_key(raw["adapter_key"])
        hosts = tuple(
            sorted({normalize_hostname(value) for value in raw["allowed_hosts"]})
        )
    except (ValidationError, TypeError, ValueError):
        raise _fail(
            "source identity, text, URL, adapter, or hosts are invalid"
        ) from None
    if raw["source_type"] not in OpportunitySource.SourceType.values:
        raise _fail("source_type is invalid")
    if not isinstance(raw["allowed_hosts"], list) or not 1 <= len(hosts) <= 20:
        raise _fail("allowed_hosts must contain 1 to 20 unique hosts")
    if url_host not in hosts:
        raise _fail("allowed_hosts must include the official URL host")
    if adapter_key not in registered_adapters():
        raise _fail(f"adapter is not registered: {adapter_key}")
    if not isinstance(raw["enabled"], bool) or not isinstance(
        raw["respect_robots_txt"], bool
    ):
        raise _fail("source flags must be boolean")
    return SourceManifestRow(
        id=identity,
        company_name=company,
        source_type=raw["source_type"],
        official_url=url,
        note=note,
        adapter_key=adapter_key,
        adapter_config=_safe_adapter_config(raw["adapter_config"]),
        enabled=raw["enabled"],
        respect_robots_txt=raw["respect_robots_txt"],
        request_interval_seconds=_bounded_int(
            raw["request_interval_seconds"],
            minimum=2,
            maximum=3600,
            field="request_interval_seconds",
        ),
        max_pages=_bounded_int(
            raw["max_pages"], minimum=1, maximum=100, field="max_pages"
        ),
        max_opportunities=_bounded_int(
            raw["max_opportunities"], minimum=1, maximum=5000, field="max_opportunities"
        ),
        max_duration_seconds=_bounded_int(
            raw["max_duration_seconds"],
            minimum=1,
            maximum=600,
            field="max_duration_seconds",
        ),
        allowed_hosts=hosts,
    )


def parse_source_manifest(payload: object) -> tuple[SourceManifestRow, ...]:
    if not isinstance(payload, dict) or set(payload) != {"schema", "sources"}:
        raise _fail("manifest must contain only schema and sources")
    if payload["schema"] != SCHEMA or not isinstance(payload["sources"], list):
        raise _fail("source manifest schema is unsupported")
    if not 1 <= len(payload["sources"]) <= MAX_SOURCES:
        raise _fail("source manifest must contain 1 to 500 sources")
    rows = tuple(_parse_row(raw) for raw in payload["sources"])
    if len({row.id for row in rows}) != len(rows):
        raise _fail("source manifest contains duplicate IDs")
    if len({row.official_url for row in rows}) != len(rows):
        raise _fail("source manifest contains duplicate official URLs")
    return rows


def build_source_manifest() -> dict[str, object]:
    sources = []
    for row in OpportunitySource.objects.prefetch_related("allowed_hosts").order_by(
        "normalized_company_name", "source_type", "id"
    ):
        sources.append(
            {
                "id": str(row.id),
                "company_name": row.company_name,
                "source_type": row.source_type,
                "official_url": row.official_url,
                "note": row.note,
                "adapter_key": row.adapter_key,
                "adapter_config": _safe_adapter_config(row.adapter_config),
                "enabled": row.enabled,
                "respect_robots_txt": row.respect_robots_txt,
                "request_interval_seconds": row.request_interval_seconds,
                "max_pages": row.max_pages,
                "max_opportunities": row.max_opportunities,
                "max_duration_seconds": row.max_duration_seconds,
                "allowed_hosts": list(
                    row.allowed_hosts.order_by("hostname").values_list(
                        "hostname", flat=True
                    )
                ),
            }
        )
    return {"schema": SCHEMA, "sources": sources}


@transaction.atomic
def apply_source_manifest(rows: tuple[SourceManifestRow, ...]) -> SourceImportResult:
    created = 0
    updated = 0
    for item in rows:
        conflict = OpportunitySource.objects.filter(
            official_url=item.official_url
        ).exclude(pk=item.id)
        if conflict.exists():
            raise _fail("an official URL is already owned by another source")
        row, was_created = OpportunitySource.objects.select_for_update().get_or_create(
            id=item.id,
            defaults={
                "company_name": item.company_name,
                "normalized_company_name": item.company_name.casefold(),
                "source_type": item.source_type,
                "official_url": item.official_url,
                "adapter_key": item.adapter_key,
            },
        )
        row.company_name = item.company_name
        row.normalized_company_name = item.company_name.casefold()
        row.source_type = item.source_type
        row.official_url = item.official_url
        row.note = item.note
        row.adapter_key = item.adapter_key
        row.adapter_config = item.adapter_config
        row.enabled = item.enabled
        row.publicly_visible = False
        row.respect_robots_txt = item.respect_robots_txt
        row.request_interval_seconds = item.request_interval_seconds
        row.max_pages = item.max_pages
        row.max_opportunities = item.max_opportunities
        row.max_duration_seconds = item.max_duration_seconds
        row.check_state = OpportunitySource.CheckState.NEVER
        row.consecutive_failures = 0
        row.last_success_at = None
        row.last_checked_at = None
        row.last_error_code = ""
        row.filter_options_stale = False
        row.last_filter_success_at = None
        row.row_version = 1
        row.save()
        OpportunitySourceHost.objects.filter(source=row).delete()
        OpportunitySourceHost.objects.bulk_create(
            [
                OpportunitySourceHost(source=row, hostname=host)
                for host in item.allowed_hosts
            ]
        )
        created += int(was_created)
        updated += int(not was_created)
    return SourceImportResult(created=created, updated=updated)


__all__ = [
    "SCHEMA",
    "SourceImportResult",
    "SourceManifestError",
    "apply_source_manifest",
    "build_source_manifest",
    "parse_source_manifest",
]
