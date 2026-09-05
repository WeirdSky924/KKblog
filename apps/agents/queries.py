from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.core.paginator import Paginator
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Sum
from django.utils import timezone

from apps.agents.models import (
    AgentEndpoint,
    AgentEndpointCheck,
    AgentInvocation,
    AgentProfile,
    AgentPromptRevision,
    AgentSitePolicy,
    AgentTokenLedger,
    AgentTokenReservation,
)
from apps.core.pagination import PageSlice
from apps.operations.public import TaskRunMetadata

from .services.common import require_administrator

_CHECK_ERROR_MESSAGES = {
    "agents.provider_auth_failed.v1": "服务器密钥无效或没有该模型的访问权限。",
    "agents.provider_request_invalid.v1": "Provider 拒绝了请求参数，请检查模型名称和输出能力。",
    "agents.provider_endpoint_not_found.v1": "接口地址或请求路径不存在。",
    "agents.secret_unavailable.v1": "服务器没有加载所选密钥。",
    "agents.credential_unavailable.v1": "自定义 API Key 无法解密或已损坏。",
    "agents.endpoint_https_required.v1": "公网接口必须使用 HTTPS。",
    "agents.request_timeout.v1": "Provider 请求超时。",
    "agents.request_network_failed.v1": "无法连接 Provider。",
    "agents.request_dns_failed.v1": "无法解析 Provider 地址。",
    "agents.response_invalid.v1": "Provider 返回内容不是有效的结构化 JSON。",
    "agents.provider_refused.v1": "Provider 拒绝了这次结构化输出请求。",
    "agents.provider_incomplete.v1": "Provider 输出被截断，未完成结构化结果。",
    "agents.response_schema_invalid.v1": "Provider 返回内容未通过结构化 schema 校验。",
    "agents.response_semantics_invalid.v1": "Provider 返回内容未通过业务语义校验。",
    "agents.schema_unavailable.v1": "所选 AGENT 的 schema 尚未在当前运行时注册。",
    "agents.profile_schema_unavailable.v1": "AGENT 的输出 schema 尚未在当前运行时注册。",
    "agents.profile_capability_unverified.v1": "请先完成当前 Endpoint 的严格 schema 能力检查。",
}


@dataclass(frozen=True, slots=True)
class AgentEndpointCheckAdminItem:
    check_id: str
    state: str
    attempt_count: int
    requested_at: datetime
    completed_at: datetime | None
    total_tokens: int | None
    safe_error_code: str
    safe_error_message: str
    schema_key: str
    capability_strategy: str
    capability_adapter_version: str
    capability_state: str


@dataclass(frozen=True, slots=True)
class AgentEndpointAdminItem:
    endpoint_id: UUID
    display_name: str
    protocol: str
    base_url: str
    model_name: str
    reasoning_effort: str
    thinking_budget_tokens: int | None
    authentication_mode: str
    secret_alias: str
    custom_api_key_present: bool
    enabled: bool
    context_window_tokens: int
    max_output_tokens: int
    per_run_token_limit: int
    request_timeout_seconds: int
    concurrency_limit: int
    daily_token_limit: int
    input_price_per_million_tokens: Decimal | None
    output_price_per_million_tokens: Decimal | None
    row_version: int
    today_effective_tokens: int
    today_reserved_tokens: int
    today_ledger_version: int
    latest_check: AgentEndpointCheckAdminItem | None


@dataclass(frozen=True, slots=True)
class AgentEndpointCapabilityOption:
    profile_key: str
    display_name: str
    schema_key: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class AgentProfileAdminItem:
    profile_id: UUID
    key: str
    display_name: str
    purpose: str
    endpoint_id: UUID
    endpoint_name: str
    schema_key: str
    enabled: bool
    current_prompt_sequence: int | None
    row_version: int


@dataclass(frozen=True, slots=True)
class AgentTokenPolicyAdminItem:
    usage_date: date
    site_daily_token_limit: int
    site_row_version: int
    site_effective_tokens: int
    site_reserved_tokens: int
    site_ledger_version: int
    endpoint_limits: tuple[tuple[UUID, int, int], ...]


@dataclass(frozen=True, slots=True)
class AgentPromptRevisionAdminItem:
    revision_id: UUID
    sequence: int
    markdown_source: str
    created_at: datetime
    is_current: bool


@dataclass(frozen=True, slots=True)
class AgentProfilePromptAdminDetail:
    profile: AgentProfileAdminItem
    revisions: tuple[AgentPromptRevisionAdminItem, ...]
    revision_page: PageSlice[AgentPromptRevisionAdminItem] | None = None


def agents_schema_ready() -> bool:
    return (
        MigrationRecorder(connection)
        .migration_qs.filter(
            app="agents",
            name="0008_agentendpoint_reasoning_effort_and_more",
        )
        .exists()
    )


def agent_profile_available(*, profile_key: str, schema_key: str) -> bool:
    if (
        not isinstance(profile_key, str)
        or not isinstance(schema_key, str)
        or not profile_key
        or not schema_key
    ):
        return False
    profile = (
        AgentProfile.objects.filter(
            key=profile_key,
            schema_key=schema_key,
            enabled=True,
            current_prompt__isnull=False,
            endpoint__enabled=True,
        )
        .select_related("endpoint")
        .first()
    )
    if profile is None:
        return False
    return AgentEndpointCheck.objects.filter(
        endpoint_id=profile.endpoint_id,
        endpoint_row_version_snapshot=profile.endpoint.row_version,
        state=AgentEndpointCheck.State.SUCCEEDED,
        schema_key_snapshot=profile.schema_key,
        capability_state="SCHEMA_SUPPORTED",
    ).exists()


def _usage_by_endpoint(usage_date) -> tuple[dict, dict, dict]:
    ledger_rows = tuple(
        AgentTokenLedger.objects.filter(
            scope=AgentTokenLedger.Scope.ENDPOINT,
            usage_date=usage_date,
        )
        .annotate(adjustment_total=Sum("adjustments__amount", default=0))
        .values(
            "endpoint_id",
            "settled_tokens",
            "adjustment_total",
            "row_version",
        )
    )
    effective = {
        row["endpoint_id"]: row["settled_tokens"] + row["adjustment_total"]
        for row in ledger_rows
    }
    versions = {row["endpoint_id"]: row["row_version"] for row in ledger_rows}
    reserved = dict(
        AgentTokenReservation.objects.filter(
            endpoint_ledger__usage_date=usage_date,
            status=AgentTokenReservation.Status.ACTIVE,
        )
        .values("endpoint_ledger__endpoint_id")
        .annotate(total=Sum("requested_tokens"))
        .values_list("endpoint_ledger__endpoint_id", "total")
    )
    return effective, reserved, versions


def _latest_checks(endpoint_ids) -> dict[UUID, AgentEndpointCheckAdminItem]:
    rows = (
        AgentEndpointCheck.objects.filter(endpoint_id__in=endpoint_ids)
        .order_by("endpoint_id", "-requested_at", "-id")
        .distinct("endpoint_id")
    )
    return {
        row.endpoint_id: AgentEndpointCheckAdminItem(
            check_id=row.id,
            state=row.state,
            attempt_count=row.attempt_count,
            requested_at=row.requested_at,
            completed_at=row.completed_at,
            total_tokens=row.total_tokens,
            safe_error_code=row.safe_error_code,
            safe_error_message=_CHECK_ERROR_MESSAGES.get(
                row.safe_error_code, "Provider 检查未成功完成。"
            ),
            schema_key=row.schema_key_snapshot,
            capability_strategy=row.capability_strategy,
            capability_adapter_version=row.capability_adapter_version,
            capability_state=row.capability_state,
        )
        for row in rows
    }


def agent_endpoint_admin_items(*, actor_id) -> tuple[AgentEndpointAdminItem, ...]:
    require_administrator(actor_id)
    usage_date = timezone.localdate()
    effective, reserved, ledger_versions = _usage_by_endpoint(usage_date)
    endpoints = tuple(AgentEndpoint.objects.all())
    latest_checks = _latest_checks(tuple(row.id for row in endpoints))
    return tuple(
        AgentEndpointAdminItem(
            endpoint_id=row.id,
            display_name=row.display_name,
            protocol=row.protocol,
            base_url=row.base_url,
            model_name=row.model_name,
            reasoning_effort=row.reasoning_effort,
            thinking_budget_tokens=row.thinking_budget_tokens,
            authentication_mode=row.authentication_mode,
            secret_alias=row.secret_alias,
            custom_api_key_present=bool(row.api_key_ciphertext),
            enabled=row.enabled,
            context_window_tokens=row.context_window_tokens,
            max_output_tokens=row.max_output_tokens,
            per_run_token_limit=row.per_run_token_limit,
            request_timeout_seconds=row.request_timeout_seconds,
            concurrency_limit=row.concurrency_limit,
            daily_token_limit=row.daily_token_limit,
            input_price_per_million_tokens=row.input_price_per_million_tokens,
            output_price_per_million_tokens=row.output_price_per_million_tokens,
            row_version=row.row_version,
            today_effective_tokens=effective.get(row.id, 0),
            today_reserved_tokens=reserved.get(row.id, 0),
            today_ledger_version=ledger_versions.get(row.id, 0),
            latest_check=latest_checks.get(row.id),
        )
        for row in endpoints
    )


def agent_profile_admin_items(*, actor_id) -> tuple[AgentProfileAdminItem, ...]:
    require_administrator(actor_id)
    rows = AgentProfile.objects.select_related("endpoint", "current_prompt")
    return tuple(
        AgentProfileAdminItem(
            profile_id=row.id,
            key=row.key,
            display_name=row.display_name,
            purpose=row.purpose,
            endpoint_id=row.endpoint_id,
            endpoint_name=row.endpoint.display_name,
            schema_key=row.schema_key,
            enabled=row.enabled,
            current_prompt_sequence=(
                row.current_prompt.sequence if row.current_prompt_id else None
            ),
            row_version=row.row_version,
        )
        for row in rows
    )


def agent_endpoint_capability_options(
    *, actor_id, endpoint_id
) -> tuple[AgentEndpointCapabilityOption, ...]:
    """Return only enabled, prompt-backed profiles owned by this Endpoint.

    The capability probe must not accept an arbitrary schema key from the
    browser.  Profile ownership and readiness are resolved from PostgreSQL,
    then the selected stable key is snapshotted into the check record.
    """
    require_administrator(actor_id)
    try:
        rows = AgentProfile.objects.filter(
            endpoint_id=endpoint_id,
            endpoint__enabled=True,
            current_prompt__isnull=False,
        ).order_by("display_name", "key")
        return tuple(
            AgentEndpointCapabilityOption(
                profile_key=row.key,
                display_name=row.display_name,
                schema_key=row.schema_key,
                enabled=row.enabled,
            )
            for row in rows
        )
    except (TypeError, ValueError):
        return ()


def agent_token_policy_admin_item(*, actor_id) -> AgentTokenPolicyAdminItem:
    require_administrator(actor_id)
    policy, _ = AgentSitePolicy.objects.get_or_create(pk=1)
    usage_date = timezone.localdate()
    try:
        site_ledger = AgentTokenLedger.objects.annotate(
            adjustment_total=Sum("adjustments__amount", default=0)
        ).get(
            scope=AgentTokenLedger.Scope.SITE,
            endpoint__isnull=True,
            usage_date=usage_date,
        )
    except AgentTokenLedger.DoesNotExist:
        site_effective = 0
        site_reserved = 0
        site_ledger_version = 0
    else:
        site_effective = site_ledger.settled_tokens + site_ledger.adjustment_total
        site_reserved = AgentTokenReservation.objects.filter(
            site_ledger=site_ledger,
            status=AgentTokenReservation.Status.ACTIVE,
        ).aggregate(total=Sum("requested_tokens", default=0))["total"]
        site_ledger_version = site_ledger.row_version
    return AgentTokenPolicyAdminItem(
        usage_date=usage_date,
        site_daily_token_limit=policy.daily_token_limit,
        site_row_version=policy.row_version,
        site_effective_tokens=site_effective,
        site_reserved_tokens=site_reserved,
        site_ledger_version=site_ledger_version,
        endpoint_limits=tuple(
            AgentEndpoint.objects.order_by("id").values_list(
                "id", "daily_token_limit", "row_version"
            )
        ),
    )


def agent_profile_prompt_admin_detail(
    *,
    actor_id,
    profile_id,
    page: int | None = None,
    page_size: int = 20,
    revision_id=None,
) -> AgentProfilePromptAdminDetail:
    require_administrator(actor_id)
    try:
        profile = AgentProfile.objects.select_related("endpoint", "current_prompt").get(
            pk=profile_id
        )
    except (AgentProfile.DoesNotExist, ValueError, TypeError):
        raise LookupError("Agent profile not found") from None
    item = AgentProfileAdminItem(
        profile_id=profile.id,
        key=profile.key,
        display_name=profile.display_name,
        purpose=profile.purpose,
        endpoint_id=profile.endpoint_id,
        endpoint_name=profile.endpoint.display_name,
        schema_key=profile.schema_key,
        enabled=profile.enabled,
        current_prompt_sequence=(
            profile.current_prompt.sequence if profile.current_prompt_id else None
        ),
        row_version=profile.row_version,
    )
    if page is not None and (
        isinstance(page, bool) or page < 1 or page_size not in (10, 20, 50)
    ):
        raise ValueError("Invalid prompt revision page")
    revisions = AgentPromptRevision.objects.filter(profile=profile).order_by(
        "-sequence"
    )
    if page is None:
        selected_revisions = tuple(revisions)
        revision_page = None
    else:
        paginator = Paginator(revisions, page_size)
        selected = paginator.get_page(page)
        selected_revisions = tuple(selected.object_list)
        required_ids = {
            str(value)
            for value in (profile.current_prompt_id, revision_id)
            if value is not None and value != ""
        }
        selected_ids = {str(row.id) for row in selected_revisions}
        missing_ids = required_ids - selected_ids
        if missing_ids:
            required_revisions = tuple(revisions.filter(pk__in=missing_ids))
            selected_revisions = (*selected_revisions, *required_revisions)
        revision_page = PageSlice(
            items=tuple(
                AgentPromptRevisionAdminItem(
                    revision_id=revision.id,
                    sequence=revision.sequence,
                    markdown_source=revision.markdown_source,
                    created_at=revision.created_at,
                    is_current=revision.id == profile.current_prompt_id,
                )
                for revision in selected.object_list
            ),
            page_number=selected.number,
            page_size=page_size,
            total_items=paginator.count,
            total_pages=paginator.num_pages,
            has_previous=selected.has_previous(),
            has_next=selected.has_next(),
        )
    return AgentProfilePromptAdminDetail(
        profile=item,
        revisions=tuple(
            AgentPromptRevisionAdminItem(
                revision_id=revision.id,
                sequence=revision.sequence,
                markdown_source=revision.markdown_source,
                created_at=revision.created_at,
                is_current=revision.id == profile.current_prompt_id,
            )
            for revision in selected_revisions
        ),
        revision_page=revision_page,
    )


def task_run_metadata(run_ids: tuple[str, ...]) -> dict[str, TaskRunMetadata]:
    if not isinstance(run_ids, tuple) or any(
        not isinstance(run_id, str) or not run_id for run_id in run_ids
    ):
        raise TypeError("run_ids must be a tuple of non-empty strings")
    invocations = {
        item.task_run_id: item
        for item in AgentInvocation.objects.filter(task_run_id__in=run_ids).only(
            "id", "task_run_id", "total_tokens"
        )
    }
    reservations = {
        item.invocation_id: item
        for item in AgentTokenReservation.objects.filter(
            invocation_id__in=[item.id for item in invocations.values()]
        ).only("invocation_id", "requested_tokens", "settled_tokens", "status")
    }
    return {
        task_run_id: TaskRunMetadata(
            token_requested=(
                reservations[invocation.id].requested_tokens
                if invocation.id in reservations
                else None
            ),
            token_settled=(
                reservations[invocation.id].settled_tokens
                if invocation.id in reservations
                else None
            ),
            token_status=(
                reservations[invocation.id].status
                if invocation.id in reservations
                else None
            ),
            invocation_total_tokens=invocation.total_tokens,
        )
        for task_run_id, invocation in invocations.items()
    }


__all__ = [
    "AgentEndpointCheckAdminItem",
    "AgentEndpointAdminItem",
    "AgentEndpointCapabilityOption",
    "AgentProfileAdminItem",
    "AgentProfilePromptAdminDetail",
    "AgentPromptRevisionAdminItem",
    "AgentTokenPolicyAdminItem",
    "agent_endpoint_admin_items",
    "agent_endpoint_capability_options",
    "agent_profile_admin_items",
    "agent_profile_prompt_admin_detail",
    "agent_token_policy_admin_item",
    "agents_schema_ready",
    "task_run_metadata",
]
