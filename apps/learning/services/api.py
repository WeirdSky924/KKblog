from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from django.db import transaction

from apps.accounts.public import is_administrator
from apps.learning.contracts import (
    DEFAULT_API_DAILY_LIMIT,
    DEFAULT_API_MINUTE_LIMIT,
    MAX_API_DAILY_LIMIT,
    MAX_API_MINUTE_LIMIT,
    MIN_API_DAILY_LIMIT,
    MIN_API_MINUTE_LIMIT,
    LearningCommandError,
    QuestionBankApiCorsMode,
)
from apps.learning.models import QuestionBankApiConfiguration
from apps.operations.public import record_audit_entry


@dataclass(frozen=True, slots=True)
class QuestionBankApiConfigurationSnapshot:
    enabled: bool
    cors_mode: str
    cors_origins: tuple[str, ...]
    minute_limit: int
    daily_limit: int
    row_version: int


def _require_administrator(actor_id) -> UUID:
    if not isinstance(actor_id, UUID) or not is_administrator(actor_id):
        raise LearningCommandError(
            "learning.administrator_required.v1", "需要管理员权限。"
        )
    return actor_id


def _snapshot(configuration: QuestionBankApiConfiguration):
    return QuestionBankApiConfigurationSnapshot(
        enabled=configuration.enabled,
        cors_mode=configuration.cors_mode,
        cors_origins=tuple(configuration.cors_origins or ()),
        minute_limit=configuration.minute_limit,
        daily_limit=configuration.daily_limit,
        row_version=configuration.row_version,
    )


def normalize_cors_origins(origins) -> tuple[str, ...]:
    if not isinstance(origins, (list, tuple)) or len(origins) > 100:
        raise LearningCommandError(
            "learning.question_bank_api_invalid.v1", "来源白名单不合法。"
        )
    normalized = []
    for value in origins:
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 255:
            raise LearningCommandError(
                "learning.question_bank_api_invalid.v1", "来源白名单不合法。"
            )
        candidate = value.strip()
        if candidate == "null" or "*" in candidate:
            raise LearningCommandError(
                "learning.question_bank_api_invalid.v1", "来源白名单不合法。"
            )
        try:
            parsed = urlsplit(candidate)
            port = parsed.port
        except ValueError:
            raise LearningCommandError(
                "learning.question_bank_api_invalid.v1", "来源白名单不合法。"
            ) from None
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or ":" in parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise LearningCommandError(
                "learning.question_bank_api_invalid.v1", "来源白名单不合法。"
            )
        hostname = parsed.hostname.encode("idna").decode("ascii").casefold()
        normalized_value = f"https://{hostname}"
        if port not in (None, 443):
            normalized_value += f":{port}"
        normalized.append(normalized_value)
    if len(set(normalized)) != len(normalized):
        raise LearningCommandError(
            "learning.question_bank_api_invalid.v1", "来源白名单不能重复。"
        )
    return tuple(normalized)


def _validate_limits(minute_limit, daily_limit) -> tuple[int, int]:
    if (
        isinstance(minute_limit, bool)
        or not isinstance(minute_limit, int)
        or not MIN_API_MINUTE_LIMIT <= minute_limit <= MAX_API_MINUTE_LIMIT
        or isinstance(daily_limit, bool)
        or not isinstance(daily_limit, int)
        or not MIN_API_DAILY_LIMIT <= daily_limit <= MAX_API_DAILY_LIMIT
        or daily_limit < minute_limit
    ):
        raise LearningCommandError(
            "learning.question_bank_api_invalid.v1", "API 限流范围不合法。"
        )
    return minute_limit, daily_limit


def question_bank_api_configuration() -> QuestionBankApiConfigurationSnapshot:
    configuration, _ = QuestionBankApiConfiguration.objects.get_or_create(pk=1)
    return _snapshot(configuration)


def configure_question_bank_api(
    *,
    actor_id,
    enabled: bool,
    cors_mode: str,
    cors_origins=(),
    minute_limit: int = DEFAULT_API_MINUTE_LIMIT,
    daily_limit: int = DEFAULT_API_DAILY_LIMIT,
    expected_version: int,
    trace_code: str,
    client_ip: str,
) -> QuestionBankApiConfigurationSnapshot:
    actor = _require_administrator(actor_id)
    if not isinstance(enabled, bool):
        raise LearningCommandError(
            "learning.question_bank_api_invalid.v1", "题库 API 开关不合法。"
        )
    try:
        normalized_mode = QuestionBankApiCorsMode(cors_mode)
    except (TypeError, ValueError):
        raise LearningCommandError(
            "learning.question_bank_api_invalid.v1",
            "题库 API 来源策略不合法。",
        ) from None
    if normalized_mode != QuestionBankApiCorsMode.ALLOWLIST:
        raise LearningCommandError(
            "learning.question_bank_api_invalid.v1",
            "当前仅支持精确来源白名单。",
        )
    normalized_origins = normalize_cors_origins(cors_origins)
    minute_limit, daily_limit = _validate_limits(minute_limit, daily_limit)
    if (
        isinstance(expected_version, bool)
        or not isinstance(expected_version, int)
        or expected_version < 1
    ):
        raise LearningCommandError(
            "learning.question_bank_api_invalid.v1", "题库 API 版本不合法。"
        )
    with transaction.atomic():
        try:
            configuration, _ = (
                QuestionBankApiConfiguration.objects.select_for_update().get_or_create(
                    pk=1,
                    defaults={
                        "enabled": False,
                        "cors_mode": QuestionBankApiCorsMode.ALLOWLIST,
                        "cors_origins": [],
                        "minute_limit": DEFAULT_API_MINUTE_LIMIT,
                        "daily_limit": DEFAULT_API_DAILY_LIMIT,
                        "row_version": 1,
                    },
                )
            )
        except (TypeError, ValueError):
            raise LearningCommandError(
                "learning.question_bank_api_unavailable.v1",
                "题库 API 配置暂不可用。",
            ) from None
        if configuration.row_version != expected_version:
            raise LearningCommandError(
                "learning.question_bank_api_conflict.v1",
                "题库 API 配置已被其他操作修改。",
            )
        before = _snapshot(configuration)
        configuration.enabled = enabled
        configuration.cors_mode = normalized_mode
        configuration.cors_origins = list(normalized_origins)
        configuration.minute_limit = minute_limit
        configuration.daily_limit = daily_limit
        configuration.row_version += 1
        configuration.save(
            update_fields=(
                "enabled",
                "cors_mode",
                "cors_origins",
                "minute_limit",
                "daily_limit",
                "row_version",
                "updated_at",
            )
        )
        after = _snapshot(configuration)
        record_audit_entry(
            action="learning.question_bank_api.update",
            actor_id=actor,
            target_id="site",
            trace_code=trace_code,
            client_ip=client_ip,
            before={
                "enabled": before.enabled,
                "cors_mode": before.cors_mode,
                "cors_origins": list(before.cors_origins),
                "minute_limit": before.minute_limit,
                "daily_limit": before.daily_limit,
                "row_version": before.row_version,
            },
            after={
                "enabled": after.enabled,
                "cors_mode": after.cors_mode,
                "cors_origins": list(after.cors_origins),
                "minute_limit": after.minute_limit,
                "daily_limit": after.daily_limit,
                "row_version": after.row_version,
            },
            summary="Update question bank API configuration",
        )
    return after


__all__ = [
    "QuestionBankApiConfigurationSnapshot",
    "configure_question_bank_api",
    "normalize_cors_origins",
    "question_bank_api_configuration",
]
