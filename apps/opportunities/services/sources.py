from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F

from apps.operations.public import record_audit_entry

from ..models import (
    Opportunity,
    OpportunityFilterKind,
    OpportunityFilterOption,
    OpportunitySource,
    OpportunitySourceFilterOption,
    OpportunitySourceHost,
)
from ..validators import (
    normalize_adapter_key,
    normalize_filter_label,
    normalize_hostname,
    normalize_opportunity_url,
    normalized_text,
    optional_text,
)
from .common import OpportunityCommandError, require_administrator, uuid_value


@dataclass(frozen=True, slots=True)
class SourceDraft:
    company_name: str
    source_type: str
    official_url: str
    note: str
    adapter_key: str
    respect_robots_txt: bool = True
    request_interval_seconds: int = 2
    max_pages: int = 50
    max_opportunities: int = 5000
    max_duration_seconds: int = 600
    allowed_hosts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceResult:
    source_id: UUID
    enabled: bool
    publicly_visible: bool
    row_version: int


@dataclass(frozen=True, slots=True)
class FilterOptionResult:
    option_id: UUID
    kind: str
    label: str


def _choice(value: str, choices, *, field: str) -> str:
    allowed = {choice for choice, _ in choices}
    if value not in allowed:
        raise OpportunityCommandError(
            "opportunities.choice_invalid.v1", f"{field}不合法。"
        )
    return value


def _positive_int(value, *, minimum: int, maximum: int, field: str) -> int:
    if isinstance(value, bool):
        raise OpportunityCommandError(
            "opportunities.source_limit_invalid.v1", f"{field}不合法。"
        )
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise OpportunityCommandError(
            "opportunities.source_limit_invalid.v1", f"{field}不合法。"
        ) from None
    if not minimum <= parsed <= maximum:
        raise OpportunityCommandError(
            "opportunities.source_limit_invalid.v1", f"{field}不合法。"
        )
    return parsed


def source_audit_snapshot(row: OpportunitySource) -> dict[str, object]:
    return {
        "company_name": row.company_name,
        "source_type": row.source_type,
        "url_host": normalize_opportunity_url(row.official_url)[1],
        "adapter_key": row.adapter_key,
        "enabled": row.enabled,
        "publicly_visible": row.publicly_visible,
        "respect_robots_txt": row.respect_robots_txt,
        "request_interval_seconds": row.request_interval_seconds,
        "max_pages": row.max_pages,
        "max_opportunities": row.max_opportunities,
        "max_duration_seconds": row.max_duration_seconds,
        "check_state": row.check_state,
        "row_version": row.row_version,
    }


def create_source(
    *,
    actor_id,
    draft: SourceDraft,
    trace_code: str,
    client_ip: str,
) -> SourceResult:
    actor = require_administrator(actor_id)
    try:
        company = normalized_text(draft.company_name, maximum=120, field="企业名称")
        source_type = _choice(
            draft.source_type,
            OpportunitySource.SourceType.choices,
            field="来源类型",
        )
        url, hostname = normalize_opportunity_url(draft.official_url)
        note = optional_text(draft.note, maximum=500, field="来源备注")
        adapter_key = normalize_adapter_key(draft.adapter_key)
        allowed_hosts = {
            normalize_hostname(value) for value in (draft.allowed_hosts or (hostname,))
        }
    except ValidationError as error:
        raise OpportunityCommandError(
            "opportunities.source_invalid.v1", str(error.message)
        ) from None
    if not isinstance(draft.respect_robots_txt, bool):
        raise OpportunityCommandError(
            "opportunities.source_robots_invalid.v1", "robots.txt 设置不合法。"
        )
    if hostname not in allowed_hosts:
        raise OpportunityCommandError(
            "opportunities.source_host_required.v1",
            "允许域名必须包含官方入口域名。",
        )
    request_interval = _positive_int(
        draft.request_interval_seconds,
        minimum=2,
        maximum=3600,
        field="请求间隔",
    )
    max_pages = _positive_int(draft.max_pages, minimum=1, maximum=100, field="页数上限")
    max_items = _positive_int(
        draft.max_opportunities,
        minimum=1,
        maximum=5000,
        field="岗位数上限",
    )
    max_duration = _positive_int(
        draft.max_duration_seconds,
        minimum=1,
        maximum=600,
        field="时长上限",
    )
    try:
        with transaction.atomic():
            row = OpportunitySource.objects.create(
                company_name=company,
                normalized_company_name=company.casefold(),
                source_type=source_type,
                official_url=url,
                note=note,
                adapter_key=adapter_key,
                respect_robots_txt=draft.respect_robots_txt,
                request_interval_seconds=request_interval,
                max_pages=max_pages,
                max_opportunities=max_items,
                max_duration_seconds=max_duration,
            )
            OpportunitySourceHost.objects.bulk_create(
                [
                    OpportunitySourceHost(source=row, hostname=value)
                    for value in sorted(allowed_hosts)
                ]
            )
            record_audit_entry(
                action="opportunities.source.create",
                actor_id=actor,
                target_id=str(row.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before={},
                after=source_audit_snapshot(row),
                summary="Create opportunity source draft",
            )
    except IntegrityError:
        raise OpportunityCommandError(
            "opportunities.source_conflict.v1", "招聘来源已存在。"
        ) from None
    return SourceResult(row.id, row.enabled, row.publicly_visible, row.row_version)


def activate_source(
    *, actor_id, source_id, trace_code: str, client_ip: str
) -> SourceResult:
    actor = require_administrator(actor_id)
    identity = uuid_value(
        source_id,
        code="opportunities.source_not_found.v1",
        message="招聘来源不存在。",
    )
    with transaction.atomic():
        try:
            row = OpportunitySource.objects.select_for_update().get(pk=identity)
        except OpportunitySource.DoesNotExist:
            raise OpportunityCommandError(
                "opportunities.source_not_found.v1", "招聘来源不存在。"
            ) from None
        before = source_audit_snapshot(row)
        if not row.enabled:
            Opportunity.objects.select_for_update().filter(
                source=row,
                source_disabled_previous_state=Opportunity.PublicationState.PUBLISHED,
            ).update(
                publication_state=Opportunity.PublicationState.PUBLISHED,
                source_disabled_previous_state=None,
            )
            row.enabled = True
            row.row_version = F("row_version") + 1
            row.save(update_fields=("enabled", "row_version", "updated_at"))
            row.refresh_from_db(fields=("row_version", "updated_at"))
            record_audit_entry(
                action="opportunities.source.activate",
                actor_id=actor,
                target_id=str(row.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before=before,
                after=source_audit_snapshot(row),
                summary="Activate opportunity source",
            )
    return SourceResult(row.id, row.enabled, row.publicly_visible, row.row_version)


def mark_source_initial_success(*, source_id, checked_at: datetime) -> SourceResult:
    identity = uuid_value(
        source_id,
        code="opportunities.source_not_found.v1",
        message="招聘来源不存在。",
    )
    if not isinstance(checked_at, datetime) or checked_at.tzinfo is None:
        raise OpportunityCommandError(
            "opportunities.checked_at_invalid.v1", "检查时间不合法。"
        )
    with transaction.atomic():
        try:
            row = OpportunitySource.objects.select_for_update().get(pk=identity)
        except OpportunitySource.DoesNotExist:
            raise OpportunityCommandError(
                "opportunities.source_not_found.v1", "招聘来源不存在。"
            ) from None
        if not row.enabled:
            raise OpportunityCommandError(
                "opportunities.source_disabled.v1", "停用来源不能公开。"
            )
        row.publicly_visible = True
        row.check_state = OpportunitySource.CheckState.HEALTHY
        row.consecutive_failures = 0
        row.last_success_at = checked_at
        row.last_checked_at = checked_at
        row.last_error_code = ""
        row.row_version = F("row_version") + 1
        row.save(
            update_fields=(
                "publicly_visible",
                "check_state",
                "consecutive_failures",
                "last_success_at",
                "last_checked_at",
                "last_error_code",
                "row_version",
                "updated_at",
            )
        )
        row.refresh_from_db(fields=("row_version", "updated_at"))
    return SourceResult(row.id, row.enabled, row.publicly_visible, row.row_version)


def replace_source_filter_options(
    *,
    source_id,
    kind: str,
    values,
    observed_at: datetime,
    complete: bool = True,
) -> tuple[FilterOptionResult, ...]:
    identity = uuid_value(
        source_id,
        code="opportunities.source_not_found.v1",
        message="招聘来源不存在。",
    )
    kind_value = _choice(kind, OpportunityFilterKind.choices, field="筛选类型")
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
        raise OpportunityCommandError(
            "opportunities.observed_at_invalid.v1", "采集时间不合法。"
        )
    try:
        normalized_values = {
            normalized: display
            for display, normalized in (
                normalize_filter_label(value) for value in values
            )
        }
    except (TypeError, ValidationError) as error:
        message = getattr(error, "message", "筛选值不合法。")
        raise OpportunityCommandError(
            "opportunities.filter_value_invalid.v1", str(message)
        ) from None
    with transaction.atomic():
        try:
            source = OpportunitySource.objects.select_for_update().get(pk=identity)
        except OpportunitySource.DoesNotExist:
            raise OpportunityCommandError(
                "opportunities.source_not_found.v1", "招聘来源不存在。"
            ) from None
        existing = {
            row.option.normalized_label: row
            for row in OpportunitySourceFilterOption.objects.select_for_update()
            .select_related("option")
            .filter(source=source, option__kind=kind_value)
        }
        results: list[FilterOptionResult] = []
        for normalized, display in sorted(normalized_values.items()):
            option, _ = OpportunityFilterOption.objects.get_or_create(
                kind=kind_value,
                normalized_label=normalized,
                defaults={"label": display},
            )
            observation = existing.pop(normalized, None)
            if observation is None:
                OpportunitySourceFilterOption.objects.create(
                    source=source,
                    option=option,
                    active=True,
                    first_observed_at=observed_at,
                    last_observed_at=observed_at,
                )
            else:
                observation.active = True
                observation.last_observed_at = observed_at
                observation.save(
                    update_fields=("active", "last_observed_at", "updated_at")
                )
            results.append(FilterOptionResult(option.id, option.kind, option.label))
        if complete:
            for observation in existing.values():
                if observation.active:
                    observation.active = False
                    observation.save(update_fields=("active", "updated_at"))
            source.filter_options_stale = False
            source.last_filter_success_at = observed_at
            source.save(
                update_fields=(
                    "filter_options_stale",
                    "last_filter_success_at",
                    "updated_at",
                )
            )
        elif not source.filter_options_stale:
            source.filter_options_stale = True
            source.save(update_fields=("filter_options_stale", "updated_at"))
    return tuple(results)


__all__ = [
    "FilterOptionResult",
    "SourceDraft",
    "SourceResult",
    "activate_source",
    "create_source",
    "mark_source_initial_success",
    "replace_source_filter_options",
    "source_audit_snapshot",
]
