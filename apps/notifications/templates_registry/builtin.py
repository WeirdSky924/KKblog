import re
from collections.abc import Callable, Iterable, Mapping
from datetime import date

from apps.core.ids import is_ulid
from apps.notifications.services.delivery import (
    NotificationRejected,
    NotificationTemplateSchema,
    register_notification_template,
)

from .registry import NotificationTemplateDefinition, register_template_definition

PayloadValidator = Callable[[Mapping[str, object]], None]
_TASK_NAME = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")
_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*\Z")
_OPERATIONAL_SOURCES = frozenset({"application", "media_disk"})
_CAPACITY_STATES = frozenset({"unknown", "normal", "warn", "no_image", "read_only"})
_HEALTH_STATES = frozenset({"unknown", "healthy", "unavailable"})


def _reject_unless(condition: bool) -> None:
    if not condition:
        raise NotificationRejected("Invalid notification payload")


def _choice(field: str, values: frozenset[str]) -> PayloadValidator:
    def validate(payload: Mapping[str, object]) -> None:
        _reject_unless(payload[field] in values)

    return validate


def _boolean(field: str) -> PayloadValidator:
    def validate(payload: Mapping[str, object]) -> None:
        _reject_unless(type(payload[field]) is bool)

    return validate


def _iso_date(field: str) -> PayloadValidator:
    def validate(payload: Mapping[str, object]) -> None:
        value = payload[field]
        try:
            parsed = date.fromisoformat(value) if isinstance(value, str) else None
        except ValueError:
            parsed = None
        _reject_unless(parsed is not None and parsed.isoformat() == value)

    return validate


def _ulid(field: str) -> PayloadValidator:
    def validate(payload: Mapping[str, object]) -> None:
        _reject_unless(isinstance(payload[field], str) and is_ulid(payload[field]))

    return validate


def _depth(payload: Mapping[str, object]) -> None:
    value = payload["depth"]
    _reject_unless(
        not isinstance(value, bool) and isinstance(value, int) and value > 100
    )


def _safe_reason(value: object, *, nullable: bool = False) -> bool:
    if nullable and value is None:
        return True
    return bool(
        isinstance(value, str)
        and len(value) <= 200
        and "\x00" not in value
        and "<" not in value
        and ">" not in value
        and "://" not in value
        and all(character.isprintable() or character in "\n\t" for character in value)
    )


def _broadcast(payload: Mapping[str, object]) -> None:
    headline = payload["headline"]
    message = payload["message"]
    _reject_unless(
        isinstance(headline, str)
        and 1 <= len(headline) <= 100
        and "\n" not in headline
        and "\r" not in headline
        and _safe_reason(headline)
    )
    _reject_unless(_safe_reason(message))


def _task_final_failure(payload: Mapping[str, object]) -> None:
    attempt = payload["attempt"]
    _reject_unless(
        isinstance(payload["task_name"], str)
        and _TASK_NAME.fullmatch(payload["task_name"])
        and not isinstance(attempt, bool)
        and attempt == 3
        and isinstance(payload["error_code"], str)
        and _ERROR_CODE.fullmatch(payload["error_code"])
    )


def _operational_state(
    payload: Mapping[str, object],
    *,
    states: frozenset[str],
) -> None:
    _reject_unless(
        payload["source_key"] in _OPERATIONAL_SOURCES
        and payload["previous_state"] in states
        and payload["current_state"] in states - {"unknown"}
        and payload["previous_state"] != payload["current_state"]
    )


def _capacity_state(payload: Mapping[str, object]) -> None:
    _operational_state(payload, states=_CAPACITY_STATES)


def _health_state(payload: Mapping[str, object]) -> None:
    _operational_state(payload, states=_HEALTH_STATES)


def _capacity_title(payload: Mapping[str, object]) -> str:
    return "磁盘容量已恢复" if payload["current_state"] == "normal" else "磁盘容量告警"


def _capacity_message(payload: Mapping[str, object]) -> str:
    messages = {
        "normal": "磁盘可用空间已恢复，创建限制已自动解除。",
        "warn": "磁盘可用空间低于 10%，请尽快处理。",
        "no_image": "磁盘可用空间低于 5%，图片创建已暂停。",
        "read_only": "磁盘可用空间低于 2%，文字和图片创建已暂停。",
    }
    return messages[payload["current_state"]]


def _health_title(payload: Mapping[str, object]) -> str:
    return "服务健康已恢复" if payload["current_state"] == "healthy" else "服务健康告警"


def _health_message(payload: Mapping[str, object]) -> str:
    return (
        "应用依赖健康检查已恢复。"
        if payload["current_state"] == "healthy"
        else "应用依赖健康检查当前不可用，请检查运行状态。"
    )


def _comment_deleted(payload: Mapping[str, object]) -> None:
    _reject_unless(payload["deleted_by_kind"] == "ADMIN")
    _reject_unless(_safe_reason(payload["reason"], nullable=True))


def _report_reviewed(payload: Mapping[str, object]) -> None:
    _reject_unless(payload["outcome"] in {"UPHELD", "REJECTED"})
    _reject_unless(_safe_reason(payload["decision_reason"]))


def _report_finalized(payload: Mapping[str, object]) -> None:
    _reject_unless(payload["outcome"] in {"FINAL_UPHELD", "FINAL_REJECTED"})
    _reject_unless(payload["recovery_status"] in {"NOT_REQUIRED", "RESTORED", "FAILED"})
    _reject_unless(_safe_reason(payload["decision_reason"]))


def _article_moderated(payload: Mapping[str, object]) -> None:
    _reject_unless(payload["action"] in {"HIDE", "DELETE"})
    _reject_unless(_safe_reason(payload["reason"]))


def _article_restored(payload: Mapping[str, object]) -> None:
    _reject_unless(payload["action"] in {"HIDE", "DELETE"})
    _reject_unless(payload["recovery_status"] == "RESTORED")


def _article_finalized(payload: Mapping[str, object]) -> None:
    _reject_unless(payload["action"] in {"HIDE", "DELETE"})
    _reject_unless(payload["outcome"] in {"FINAL_UPHELD", "FINAL_REJECTED"})
    _reject_unless(payload["recovery_status"] in {"NOT_REQUIRED", "RESTORED", "FAILED"})
    _reject_unless(_safe_reason(payload["decision_reason"]))


def _reason_message(base: str, payload: Mapping[str, object], field: str) -> str:
    reason = payload[field]
    return f"{base} 原因：{reason}" if reason else base


def _role_message(payload: Mapping[str, object]) -> str:
    return "你已获得作者权限。" if payload["enabled"] else "你的作者权限已被撤销。"


def _tag_review_message(payload: Mapping[str, object]) -> str:
    return (
        "你提交的标签已通过审核。"
        if payload["outcome"] == "approved"
        else "你提交的标签未通过审核。"
    )


def _comment_deleted_message(payload: Mapping[str, object]) -> str:
    return _reason_message("你的评论已被管理员删除。", payload, "reason")


def _report_review_message(payload: Mapping[str, object]) -> str:
    outcome = "举报成立。" if payload["outcome"] == "UPHELD" else "举报未成立。"
    return _reason_message(outcome, payload, "decision_reason")


def _report_final_message(payload: Mapping[str, object]) -> str:
    outcome = (
        "申诉终局维持原处理。"
        if payload["outcome"] == "FINAL_UPHELD"
        else "申诉终局已变更原处理。"
    )
    return _reason_message(outcome, payload, "decision_reason")


def _article_action_message(payload: Mapping[str, object]) -> str:
    action = "隐藏" if payload["action"] == "HIDE" else "删除"
    return _reason_message(f"你的文章已被管理员{action}。", payload, "reason")


def _article_final_message(payload: Mapping[str, object]) -> str:
    outcome = (
        "申诉终局维持原处理。"
        if payload["outcome"] == "FINAL_UPHELD"
        else "申诉终局已变更原处理。"
    )
    return _reason_message(outcome, payload, "decision_reason")


def _schema(
    key: str,
    target_type: str,
    fields: frozenset[str],
    validator: PayloadValidator,
) -> NotificationTemplateSchema:
    return NotificationTemplateSchema(
        key=key,
        target_type=target_type,
        allowed_payload_fields=fields,
        required_payload_fields=fields,
        payload_validator=validator,
    )


_BUILTINS = (
    (
        _schema(
            "capacity.threshold_changed.v1",
            "operational_state",
            frozenset({"source_key", "previous_state", "current_state"}),
            _capacity_state,
        ),
        NotificationTemplateDefinition(
            "capacity.threshold_changed.v1",
            _capacity_title,
            _capacity_message,
        ),
    ),
    (
        _schema(
            "service.health_changed.v1",
            "operational_state",
            frozenset({"source_key", "previous_state", "current_state"}),
            _health_state,
        ),
        NotificationTemplateDefinition(
            "service.health_changed.v1",
            _health_title,
            _health_message,
        ),
    ),
    (
        _schema(
            "task.final_failed.v1",
            "task_run",
            frozenset({"task_name", "attempt", "error_code"}),
            _task_final_failure,
        ),
        NotificationTemplateDefinition(
            "task.final_failed.v1",
            "后台任务最终失败",
            lambda payload: (
                f"任务 {payload['task_name']} 已在第 3 次尝试后终止，"
                f"错误码：{payload['error_code']}。"
            ),
        ),
    ),
    (
        _schema(
            "admin.broadcast.v1",
            "broadcast",
            frozenset({"headline", "message"}),
            _broadcast,
        ),
        NotificationTemplateDefinition(
            "admin.broadcast.v1",
            lambda payload: payload["headline"],
            lambda payload: payload["message"],
        ),
    ),
    (
        _schema(
            "account.author_role_changed.v1",
            "account_role",
            frozenset({"enabled"}),
            _boolean("enabled"),
        ),
        NotificationTemplateDefinition(
            "account.author_role_changed.v1", "作者权限已更新", _role_message
        ),
    ),
    (
        _schema(
            "tag.reviewed.v1",
            "tag",
            frozenset({"outcome"}),
            _choice("outcome", frozenset({"approved", "rejected"})),
        ),
        NotificationTemplateDefinition(
            "tag.reviewed.v1", "标签审核结果", _tag_review_message
        ),
    ),
    (
        _schema(
            "tag.restore_conflict.v1",
            "tag",
            frozenset({"article_id"}),
            _ulid("article_id"),
        ),
        NotificationTemplateDefinition(
            "tag.restore_conflict.v1",
            "标签关联恢复失败",
            lambda payload: "一篇文章已达到标签数量上限，关联未能恢复。",
        ),
    ),
    (
        _schema(
            "article.admin_viewed.v1",
            "article",
            frozenset({"view_date"}),
            _iso_date("view_date"),
        ),
        NotificationTemplateDefinition(
            "article.admin_viewed.v1",
            "管理员查看了文章",
            lambda payload: "管理员查看了你的文章。",
        ),
    ),
    (
        _schema(
            "comment.deep_thread.v1", "discussion_thread", frozenset({"depth"}), _depth
        ),
        NotificationTemplateDefinition(
            "comment.deep_thread.v1",
            "讨论层级提醒",
            lambda payload: "讨论回复层级已超过 100 层。",
        ),
    ),
    (
        _schema(
            "comment.deleted.v1",
            "comment",
            frozenset({"deleted_by_kind", "reason"}),
            _comment_deleted,
        ),
        NotificationTemplateDefinition(
            "comment.deleted.v1", "评论已被管理员删除", _comment_deleted_message
        ),
    ),
    (
        _schema(
            "report.reviewed.v1",
            "report",
            frozenset({"outcome", "decision_reason"}),
            _report_reviewed,
        ),
        NotificationTemplateDefinition(
            "report.reviewed.v1", "举报审核结果", _report_review_message
        ),
    ),
    (
        _schema(
            "report.finalized.v1",
            "report",
            frozenset({"outcome", "decision_reason", "recovery_status"}),
            _report_finalized,
        ),
        NotificationTemplateDefinition(
            "report.finalized.v1", "举报申诉终局", _report_final_message
        ),
    ),
    (
        _schema(
            "report.closed.v1",
            "report",
            frozenset({"outcome"}),
            _choice("outcome", frozenset({"CONTENT_DELETED"})),
        ),
        NotificationTemplateDefinition(
            "report.closed.v1",
            "举报已结案",
            lambda payload: "相关内容已删除，举报已结案。",
        ),
    ),
    (
        _schema(
            "article.moderated.v1",
            "article",
            frozenset({"action", "reason"}),
            _article_moderated,
        ),
        NotificationTemplateDefinition(
            "article.moderated.v1", "文章已被管理员处理", _article_action_message
        ),
    ),
    (
        _schema(
            "article.moderation_restored.v1",
            "article",
            frozenset({"action", "recovery_status"}),
            _article_restored,
        ),
        NotificationTemplateDefinition(
            "article.moderation_restored.v1",
            "文章管理措施已恢复",
            lambda payload: "你的文章已恢复到处理前状态。",
        ),
    ),
    (
        _schema(
            "article.moderation_finalized.v1",
            "article",
            frozenset({"action", "outcome", "decision_reason", "recovery_status"}),
            _article_finalized,
        ),
        NotificationTemplateDefinition(
            "article.moderation_finalized.v1", "文章申诉终局", _article_final_message
        ),
    ),
)

BUILTIN_TEMPLATE_KEYS = frozenset(schema.key for schema, _definition in _BUILTINS)


def register_builtin_templates(*, keys: Iterable[str] | None = None) -> None:
    selected = BUILTIN_TEMPLATE_KEYS if keys is None else frozenset(keys)
    if not selected <= BUILTIN_TEMPLATE_KEYS:
        raise NotificationRejected("Unknown builtin notification template")
    for schema, definition in _BUILTINS:
        if schema.key not in selected:
            continue
        register_notification_template(schema, replace=True)
        register_template_definition(definition, replace=True)
