import re
from dataclasses import dataclass
from hashlib import sha256

from django.db import IntegrityError, transaction
from django.db.models import Max

from apps.agents.contracts import AgentCommandError
from apps.agents.models import (
    AgentEndpoint,
    AgentEndpointCheck,
    AgentProfile,
    AgentPromptRevision,
)
from apps.agents.schemas import SchemaValidationError, structured_schema
from apps.operations.public import record_audit_entry

from .common import (
    require_administrator,
    uuid_value,
    validate_profile_key,
    validate_schema_key,
    visible_text,
)

_PROMPT_LIMIT_BYTES = 65_536
_PROMPT_VARIABLE = re.compile(r"{{\s*([a-z][a-z0-9_]*)\s*}}")
_PURPOSE_VARIABLES = {
    AgentProfile.Purpose.KNOWLEDGE_REVIEW: frozenset(
        {"document_block", "block_index", "block_count"}
    ),
    AgentProfile.Purpose.QUESTION_GENERATION: frozenset(
        {
            "document_block",
            "knowledge_points",
            "question_types",
            "question_limit",
            "tag_candidates",
        }
    ),
}


@dataclass(frozen=True, slots=True)
class ProfileDraft:
    key: str
    display_name: str
    purpose: str
    endpoint_id: object
    schema_key: str
    enabled: bool = False


def profile_audit_snapshot(profile: AgentProfile) -> dict[str, object]:
    sequence = None
    if profile.current_prompt_id:
        sequence = profile.current_prompt.sequence
    return {
        "profile_key": profile.key,
        "purpose": profile.purpose,
        "endpoint_id": str(profile.endpoint_id),
        "schema_key": profile.schema_key,
        "enabled": profile.enabled,
        "current_prompt_sequence": sequence,
        "row_version": profile.row_version,
    }


def _ensure_schema_registered(schema_key: str) -> None:
    try:
        structured_schema(schema_key)
    except SchemaValidationError:
        raise AgentCommandError(
            "agents.profile_schema_unavailable.v1",
            "AGENT 的输出 schema 尚未在当前运行时注册。",
        ) from None


def _ensure_capability_probe(schema_key: str, endpoint: AgentEndpoint) -> None:
    supported = AgentEndpointCheck.objects.filter(
        endpoint=endpoint,
        endpoint_row_version_snapshot=endpoint.row_version,
        state=AgentEndpointCheck.State.SUCCEEDED,
        schema_key_snapshot=schema_key,
        capability_state="SCHEMA_SUPPORTED",
    ).exists()
    if not supported:
        raise AgentCommandError(
            "agents.profile_capability_unverified.v1",
            "请先对当前 Endpoint 执行一次该 schema 的严格能力检查。",
        )


def create_agent_profile(
    *, actor_id, draft: ProfileDraft, trace_code: str, client_ip: str
) -> AgentProfile:
    actor = require_administrator(actor_id)
    if (
        not isinstance(draft, ProfileDraft)
        or draft.purpose not in AgentProfile.Purpose.values
    ):
        raise AgentCommandError("agents.profile_invalid.v1", "AGENT 配置不合法。")
    if draft.enabled:
        raise AgentCommandError(
            "agents.profile_prompt_required.v1", "新 AGENT 保存 Prompt 后才能启用。"
        )
    endpoint_id = uuid_value(
        draft.endpoint_id,
        code="agents.endpoint_not_found.v1",
        message="Endpoint 不存在。",
    )
    try:
        with transaction.atomic():
            try:
                endpoint = AgentEndpoint.objects.get(pk=endpoint_id)
            except AgentEndpoint.DoesNotExist:
                raise AgentCommandError(
                    "agents.endpoint_not_found.v1", "Endpoint 不存在。"
                ) from None
            profile = AgentProfile.objects.create(
                key=validate_profile_key(draft.key),
                display_name=visible_text(
                    draft.display_name, field="AGENT 名称", maximum=80
                ),
                purpose=draft.purpose,
                endpoint=endpoint,
                schema_key=validate_schema_key(draft.schema_key),
                enabled=False,
            )
            record_audit_entry(
                action="agents.profile.create",
                actor_id=actor,
                target_id=str(profile.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before={},
                after=profile_audit_snapshot(profile),
                summary="Create agent profile",
            )
    except IntegrityError as exc:
        raise AgentCommandError(
            "agents.profile_conflict.v1", "AGENT 标识已存在。"
        ) from exc
    return profile


def _validated_prompt(source: object, purpose: str) -> tuple[str, str]:
    if not isinstance(source, str) or not source.strip() or "\x00" in source:
        raise AgentCommandError("agents.prompt_invalid.v1", "Prompt 内容不合法。")
    encoded = source.encode("utf-8")
    if len(encoded) > _PROMPT_LIMIT_BYTES:
        raise AgentCommandError("agents.prompt_invalid.v1", "Prompt 内容过大。")
    variables = frozenset(_PROMPT_VARIABLE.findall(source))
    without_variables = _PROMPT_VARIABLE.sub("", source)
    if (
        not variables <= _PURPOSE_VARIABLES[purpose]
        or "{{" in without_variables
        or "}}" in without_variables
    ):
        raise AgentCommandError(
            "agents.prompt_variable_invalid.v1", "Prompt 包含未注册变量。"
        )
    return source, sha256(encoded).hexdigest()


def save_agent_prompt_revision(
    *,
    actor_id,
    profile_id,
    markdown_source: str,
    expected_profile_version: int,
    trace_code: str,
    client_ip: str,
) -> AgentPromptRevision:
    actor = require_administrator(actor_id)
    identity = uuid_value(
        profile_id, code="agents.profile_not_found.v1", message="AGENT 不存在。"
    )
    with transaction.atomic():
        try:
            profile = AgentProfile.objects.select_for_update().get(pk=identity)
        except AgentProfile.DoesNotExist:
            raise AgentCommandError(
                "agents.profile_not_found.v1", "AGENT 不存在。"
            ) from None
        if profile.row_version != expected_profile_version:
            raise AgentCommandError(
                "agents.configuration_conflict.v1", "AGENT 已被其他操作修改。"
            )
        source, digest = _validated_prompt(markdown_source, profile.purpose)
        before = profile_audit_snapshot(profile)
        sequence = (
            profile.prompt_revisions.aggregate(value=Max("sequence"))["value"] or 0
        ) + 1
        revision = AgentPromptRevision.objects.create(
            profile=profile,
            sequence=sequence,
            markdown_source=source,
            content_sha256=digest,
            created_by_id=actor,
        )
        profile.current_prompt = revision
        profile.row_version += 1
        profile.save(update_fields=("current_prompt", "row_version", "updated_at"))
        record_audit_entry(
            action="agents.prompt.save",
            actor_id=actor,
            target_id=str(profile.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after=profile_audit_snapshot(profile),
            summary="Save agent prompt revision",
        )
    return revision


def set_agent_profile_enabled(
    *,
    actor_id,
    profile_id,
    enabled: bool,
    expected_version: int,
    trace_code: str,
    client_ip: str,
) -> AgentProfile:
    actor = require_administrator(actor_id)
    identity = uuid_value(
        profile_id, code="agents.profile_not_found.v1", message="AGENT 不存在。"
    )
    if not isinstance(enabled, bool):
        raise AgentCommandError("agents.profile_invalid.v1", "启用状态不合法。")
    with transaction.atomic():
        try:
            profile = (
                AgentProfile.objects.select_for_update()
                .select_related("endpoint")
                .get(pk=identity)
            )
        except AgentProfile.DoesNotExist:
            raise AgentCommandError(
                "agents.profile_not_found.v1", "AGENT 不存在。"
            ) from None
        if profile.row_version != expected_version:
            raise AgentCommandError(
                "agents.configuration_conflict.v1", "AGENT 已被其他操作修改。"
            )
        if enabled and (
            profile.current_prompt_id is None or not profile.endpoint.enabled
        ):
            raise AgentCommandError(
                "agents.profile_not_ready.v1", "AGENT 缺少可用 Prompt 或 Endpoint。"
            )
        if enabled:
            _ensure_schema_registered(profile.schema_key)
            _ensure_capability_probe(profile.schema_key, profile.endpoint)
        before = profile_audit_snapshot(profile)
        profile.enabled = enabled
        profile.row_version += 1
        profile.save(update_fields=("enabled", "row_version", "updated_at"))
        record_audit_entry(
            action="agents.profile.enabled",
            actor_id=actor,
            target_id=str(profile.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after=profile_audit_snapshot(profile),
            summary="Set agent profile enabled",
        )
    return profile


def update_agent_profile(
    *,
    actor_id,
    profile_id,
    draft: ProfileDraft,
    expected_version: int,
    trace_code: str,
    client_ip: str,
) -> AgentProfile:
    actor = require_administrator(actor_id)
    identity = uuid_value(
        profile_id, code="agents.profile_not_found.v1", message="AGENT 不存在。"
    )
    if (
        not isinstance(draft, ProfileDraft)
        or draft.purpose not in AgentProfile.Purpose.values
    ):
        raise AgentCommandError("agents.profile_invalid.v1", "AGENT 配置不合法。")
    endpoint_id = uuid_value(
        draft.endpoint_id,
        code="agents.endpoint_not_found.v1",
        message="Endpoint 不存在。",
    )
    with transaction.atomic():
        try:
            profile = AgentProfile.objects.select_for_update().get(pk=identity)
            endpoint = AgentEndpoint.objects.get(pk=endpoint_id)
        except AgentProfile.DoesNotExist:
            raise AgentCommandError(
                "agents.profile_not_found.v1", "AGENT 不存在。"
            ) from None
        except AgentEndpoint.DoesNotExist:
            raise AgentCommandError(
                "agents.endpoint_not_found.v1", "Endpoint 不存在。"
            ) from None
        if profile.row_version != expected_version:
            raise AgentCommandError(
                "agents.configuration_conflict.v1", "AGENT 已被其他操作修改。"
            )
        stable_schema_key = validate_schema_key(draft.schema_key)
        if validate_profile_key(draft.key) != profile.key:
            raise AgentCommandError(
                "agents.profile_key_immutable.v1", "AGENT 稳定标识不能修改。"
            )
        if draft.enabled and (
            profile.current_prompt_id is None or not endpoint.enabled
        ):
            raise AgentCommandError(
                "agents.profile_not_ready.v1", "AGENT 缺少可用 Prompt 或 Endpoint。"
            )
        if draft.enabled:
            _ensure_schema_registered(stable_schema_key)
            _ensure_capability_probe(stable_schema_key, endpoint)
        if profile.current_prompt_id:
            _validated_prompt(profile.current_prompt.markdown_source, draft.purpose)
        before = profile_audit_snapshot(profile)
        profile.display_name = visible_text(
            draft.display_name, field="AGENT 名称", maximum=80
        )
        profile.purpose = draft.purpose
        profile.endpoint = endpoint
        profile.schema_key = stable_schema_key
        profile.enabled = draft.enabled
        profile.row_version += 1
        profile.save()
        record_audit_entry(
            action="agents.profile.update",
            actor_id=actor,
            target_id=str(profile.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after=profile_audit_snapshot(profile),
            summary="Update agent profile",
        )
    return profile


def switch_agent_prompt_revision(
    *,
    actor_id,
    profile_id,
    prompt_revision_id,
    expected_version,
    trace_code,
    client_ip,
) -> AgentProfile:
    actor = require_administrator(actor_id)
    identity = uuid_value(
        profile_id, code="agents.profile_not_found.v1", message="AGENT 不存在。"
    )
    revision_identity = uuid_value(
        prompt_revision_id,
        code="agents.prompt_not_found.v1",
        message="Prompt 修订不存在。",
    )
    with transaction.atomic():
        try:
            profile = AgentProfile.objects.select_for_update().get(pk=identity)
            revision = AgentPromptRevision.objects.get(pk=revision_identity)
        except AgentProfile.DoesNotExist:
            raise AgentCommandError(
                "agents.profile_not_found.v1", "AGENT 不存在。"
            ) from None
        except AgentPromptRevision.DoesNotExist:
            raise AgentCommandError(
                "agents.prompt_not_found.v1", "Prompt 修订不存在。"
            ) from None
        if profile.row_version != expected_version:
            raise AgentCommandError(
                "agents.configuration_conflict.v1", "AGENT 已被其他操作修改。"
            )
        if revision.profile_id != profile.id:
            raise AgentCommandError("agents.prompt_not_found.v1", "Prompt 修订不存在。")
        before = profile_audit_snapshot(profile)
        profile.current_prompt = revision
        profile.row_version += 1
        profile.save(update_fields=("current_prompt", "row_version", "updated_at"))
        record_audit_entry(
            action="agents.prompt.switch",
            actor_id=actor,
            target_id=str(profile.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after=profile_audit_snapshot(profile),
            summary="Switch agent prompt revision",
        )
    return profile


__all__ = [
    "ProfileDraft",
    "create_agent_profile",
    "profile_audit_snapshot",
    "save_agent_prompt_revision",
    "set_agent_profile_enabled",
    "switch_agent_prompt_revision",
    "update_agent_profile",
]
