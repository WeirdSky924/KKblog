from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction

from apps.agents.contracts import (
    DEFAULT_ENDPOINT_DAILY_TOKEN_LIMIT,
    DEFAULT_SITE_DAILY_TOKEN_LIMIT,
    AgentCommandError,
    EndpointRuntimeSettings,
    default_endpoint_base_url,
    validate_site_daily_token_limit,
)
from apps.agents.credentials import AgentCredentialError, encrypt_api_key
from apps.agents.models import AgentEndpoint, AgentSitePolicy
from apps.agents.providers.capabilities import validate_reasoning_settings
from apps.operations.public import record_audit_entry

from .common import (
    normalize_base_url,
    require_administrator,
    uuid_value,
    validate_secret_alias,
    visible_text,
)


@dataclass(frozen=True, slots=True)
class EndpointDraft:
    display_name: str
    protocol: str
    base_url: str
    model_name: str
    authentication_mode: str
    secret_alias: str = ""
    api_key: str = field(default="", repr=False)
    clear_api_key: bool = False
    enabled: bool = False
    runtime: EndpointRuntimeSettings = field(default_factory=EndpointRuntimeSettings)
    input_price_per_million_tokens: Decimal | str | None = None
    output_price_per_million_tokens: Decimal | str | None = None


def _price(value: object, *, field_name: str) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise AgentCommandError("agents.price_invalid.v1", f"{field_name}不合法。")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise AgentCommandError(
            "agents.price_invalid.v1", f"{field_name}不合法。"
        ) from None
    if not parsed.is_finite() or parsed < 0 or parsed >= Decimal("100000000"):
        raise AgentCommandError("agents.price_invalid.v1", f"{field_name}不合法。")
    return parsed


def _validated(
    draft: EndpointDraft,
    *,
    site_limit: int,
    existing_api_key_ciphertext: str = "",
) -> dict[str, object]:
    if not isinstance(draft, EndpointDraft):
        raise AgentCommandError(
            "agents.configuration_invalid.v1", "Endpoint 配置不合法。"
        )
    if draft.protocol not in AgentEndpoint.Protocol.values:
        raise AgentCommandError("agents.protocol_invalid.v1", "Endpoint 协议不合法。")
    if draft.authentication_mode not in AgentEndpoint.AuthenticationMode.values:
        raise AgentCommandError("agents.authentication_invalid.v1", "认证方式不合法。")
    if not isinstance(draft.enabled, bool):
        raise AgentCommandError("agents.configuration_invalid.v1", "启用状态不合法。")
    if not isinstance(draft.clear_api_key, bool):
        raise AgentCommandError(
            "agents.configuration_invalid.v1", "密钥清除状态不合法。"
        )
    secret_alias = ""
    if draft.authentication_mode == AgentEndpoint.AuthenticationMode.SECRET_ALIAS:
        secret_alias = validate_secret_alias(draft.secret_alias)
    elif draft.authentication_mode == AgentEndpoint.AuthenticationMode.CUSTOM_API_KEY:
        if draft.secret_alias:
            raise AgentCommandError(
                "agents.secret_alias_invalid.v1",
                "自定义 API Key 不能同时使用服务器密钥别名。",
            )
        if draft.api_key and draft.clear_api_key:
            raise AgentCommandError(
                "agents.api_key_invalid.v1", "不能同时更新和清除自定义 API Key。"
            )
        if draft.api_key:
            try:
                api_key_ciphertext = encrypt_api_key(draft.api_key)
            except AgentCredentialError as error:
                raise AgentCommandError(
                    error.args[0], "API Key 不合法或服务端加密配置不可用。"
                ) from None
        elif existing_api_key_ciphertext and not draft.clear_api_key:
            api_key_ciphertext = existing_api_key_ciphertext
        else:
            raise AgentCommandError(
                "agents.api_key_required.v1", "自定义认证必须提供 API Key。"
            )
    elif draft.secret_alias:
        raise AgentCommandError(
            "agents.secret_alias_invalid.v1", "无认证 Endpoint 不能保存密钥引用。"
        )
    elif draft.api_key:
        raise AgentCommandError(
            "agents.api_key_invalid.v1", "只有自定义 API Key 认证可以保存 API Key。"
        )
    if draft.authentication_mode != AgentEndpoint.AuthenticationMode.CUSTOM_API_KEY:
        api_key_ciphertext = ""
    runtime = draft.runtime.validate(site_daily_token_limit=site_limit)
    base_url = draft.base_url.strip() if isinstance(draft.base_url, str) else ""
    if not base_url:
        base_url = default_endpoint_base_url(draft.protocol)
    validate_reasoning_settings(
        protocol=draft.protocol,
        model_name=draft.model_name,
        reasoning_effort=runtime.reasoning_effort,
        thinking_budget_tokens=runtime.thinking_budget_tokens,
        max_output_tokens=runtime.max_output_tokens,
    )
    return {
        "display_name": visible_text(draft.display_name, field="显示名称", maximum=80),
        "protocol": draft.protocol,
        "base_url": normalize_base_url(base_url),
        "model_name": visible_text(draft.model_name, field="模型名称", maximum=160),
        "authentication_mode": draft.authentication_mode,
        "secret_alias": secret_alias,
        "api_key_ciphertext": api_key_ciphertext,
        "enabled": draft.enabled,
        **runtime.as_dict(),
        "daily_token_limit": runtime.endpoint_daily_token_limit,
        "input_price_per_million_tokens": _price(
            draft.input_price_per_million_tokens, field_name="输入价格"
        ),
        "output_price_per_million_tokens": _price(
            draft.output_price_per_million_tokens, field_name="输出价格"
        ),
    }


def endpoint_audit_snapshot(endpoint: AgentEndpoint) -> dict[str, object]:
    return {
        "protocol": endpoint.protocol,
        "authentication_mode": endpoint.authentication_mode,
        "authentication_reference_present": bool(
            endpoint.secret_alias or endpoint.api_key_ciphertext
        ),
        "model_configured": bool(endpoint.model_name),
        "enabled": endpoint.enabled,
        "context_window_units": endpoint.context_window_tokens,
        "max_output_units": endpoint.max_output_tokens,
        "per_run_unit_limit": endpoint.per_run_token_limit,
        "request_timeout_seconds": endpoint.request_timeout_seconds,
        "concurrency_limit": endpoint.concurrency_limit,
        "daily_unit_limit": endpoint.daily_token_limit,
        "reasoning_effort": endpoint.reasoning_effort,
        "thinking_budget": endpoint.thinking_budget_tokens,
        "row_version": endpoint.row_version,
    }


def _site_policy(*, lock: bool = False) -> AgentSitePolicy:
    AgentSitePolicy.objects.get_or_create(pk=1)
    query = (
        AgentSitePolicy.objects.select_for_update() if lock else AgentSitePolicy.objects
    )
    return query.get(pk=1)


def create_agent_endpoint(
    *, actor_id, draft: EndpointDraft, trace_code: str, client_ip: str
) -> AgentEndpoint:
    actor = require_administrator(actor_id)
    try:
        with transaction.atomic():
            policy = _site_policy(lock=True)
            values = _validated(draft, site_limit=policy.daily_token_limit)
            values.pop("endpoint_daily_token_limit")
            endpoint = AgentEndpoint.objects.create(**values)
            record_audit_entry(
                action="agents.endpoint.create",
                actor_id=actor,
                target_id=str(endpoint.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before={},
                after=endpoint_audit_snapshot(endpoint),
                summary="Create agent endpoint",
            )
    except IntegrityError as exc:
        raise AgentCommandError(
            "agents.endpoint_conflict.v1", "Endpoint 名称已存在。"
        ) from exc
    return endpoint


def update_agent_endpoint(
    *,
    actor_id,
    endpoint_id,
    draft: EndpointDraft,
    expected_version: int,
    trace_code: str,
    client_ip: str,
) -> AgentEndpoint:
    actor = require_administrator(actor_id)
    identity = uuid_value(
        endpoint_id,
        code="agents.endpoint_not_found.v1",
        message="Endpoint 不存在。",
    )
    try:
        with transaction.atomic():
            policy = _site_policy(lock=True)
            try:
                endpoint = AgentEndpoint.objects.select_for_update().get(pk=identity)
            except AgentEndpoint.DoesNotExist:
                raise AgentCommandError(
                    "agents.endpoint_not_found.v1", "Endpoint 不存在。"
                ) from None
            if endpoint.row_version != expected_version:
                raise AgentCommandError(
                    "agents.configuration_conflict.v1", "Endpoint 已被其他操作修改。"
                )
            values = _validated(
                draft,
                site_limit=policy.daily_token_limit,
                existing_api_key_ciphertext=endpoint.api_key_ciphertext,
            )
            values.pop("endpoint_daily_token_limit")
            before = endpoint_audit_snapshot(endpoint)
            for name, value in values.items():
                setattr(endpoint, name, value)
            endpoint.row_version += 1
            endpoint.save()
            record_audit_entry(
                action="agents.endpoint.update",
                actor_id=actor,
                target_id=str(endpoint.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before=before,
                after=endpoint_audit_snapshot(endpoint),
                summary="Update agent endpoint",
            )
    except IntegrityError as exc:
        raise AgentCommandError(
            "agents.endpoint_conflict.v1", "Endpoint 名称已存在。"
        ) from exc
    return endpoint


def _site_policy_audit_snapshot(
    policy: AgentSitePolicy, *, endpoint_count: int
) -> dict[str, object]:
    return {
        "site_daily_units": policy.daily_token_limit,
        "endpoint_count": endpoint_count,
        "row_version": policy.row_version,
    }


def update_site_daily_token_limit(
    *,
    actor_id,
    daily_token_limit,
    expected_version,
    trace_code,
    client_ip,
) -> AgentSitePolicy:
    actor = require_administrator(actor_id)
    limit = validate_site_daily_token_limit(daily_token_limit)
    with transaction.atomic():
        policy = _site_policy(lock=True)
        endpoints = list(AgentEndpoint.objects.select_for_update().all())
        if policy.row_version != expected_version:
            raise AgentCommandError(
                "agents.configuration_conflict.v1", "全站 token 设置已被修改。"
            )
        if any(endpoint.daily_token_limit > limit for endpoint in endpoints):
            raise AgentCommandError(
                "agents.site_limit_conflict.v1",
                "全站上限不能低于现有 Endpoint 上限。",
            )
        before = _site_policy_audit_snapshot(policy, endpoint_count=len(endpoints))
        policy.daily_token_limit = limit
        policy.row_version += 1
        policy.save(update_fields=("daily_token_limit", "row_version", "updated_at"))
        record_audit_entry(
            action="agents.token_limits.update",
            actor_id=actor,
            target_id=str(policy.pk),
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after=_site_policy_audit_snapshot(policy, endpoint_count=len(endpoints)),
            summary="Update agent site token limit",
        )
    return policy


def restore_default_token_limits(
    *,
    actor_id,
    expected_site_version,
    expected_endpoint_versions,
    trace_code,
    client_ip,
) -> AgentSitePolicy:
    actor = require_administrator(actor_id)
    if not isinstance(expected_endpoint_versions, dict):
        raise AgentCommandError(
            "agents.configuration_conflict.v1", "Endpoint 版本集合不合法。"
        )
    normalized_versions = {
        uuid_value(
            endpoint_id,
            code="agents.configuration_conflict.v1",
            message="Endpoint 版本集合不合法。",
        ): version
        for endpoint_id, version in expected_endpoint_versions.items()
    }
    with transaction.atomic():
        policy = _site_policy(lock=True)
        endpoints = list(AgentEndpoint.objects.select_for_update().order_by("id"))
        if policy.row_version != expected_site_version or set(normalized_versions) != {
            endpoint.id for endpoint in endpoints
        }:
            raise AgentCommandError(
                "agents.configuration_conflict.v1", "token 设置已被其他操作修改。"
            )
        if any(
            normalized_versions[endpoint.id] != endpoint.row_version
            for endpoint in endpoints
        ):
            raise AgentCommandError(
                "agents.configuration_conflict.v1", "token 设置已被其他操作修改。"
            )
        if any(
            endpoint.per_run_token_limit > DEFAULT_ENDPOINT_DAILY_TOKEN_LIMIT
            for endpoint in endpoints
        ):
            raise AgentCommandError(
                "agents.default_limit_conflict.v1",
                "现有 Endpoint 单次业务上限高于默认每日上限。",
            )
        before = _site_policy_audit_snapshot(policy, endpoint_count=len(endpoints))
        policy.daily_token_limit = DEFAULT_SITE_DAILY_TOKEN_LIMIT
        policy.row_version += 1
        policy.save(update_fields=("daily_token_limit", "row_version", "updated_at"))
        for endpoint in endpoints:
            endpoint.daily_token_limit = DEFAULT_ENDPOINT_DAILY_TOKEN_LIMIT
            endpoint.row_version += 1
            endpoint.save(
                update_fields=("daily_token_limit", "row_version", "updated_at")
            )
        record_audit_entry(
            action="agents.token_limits.restore_defaults",
            actor_id=actor,
            target_id=str(policy.pk),
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after=_site_policy_audit_snapshot(policy, endpoint_count=len(endpoints)),
            summary="Restore default agent token limits",
        )
    return policy


__all__ = [
    "EndpointDraft",
    "create_agent_endpoint",
    "endpoint_audit_snapshot",
    "restore_default_token_limits",
    "update_agent_endpoint",
    "update_site_daily_token_limit",
]
