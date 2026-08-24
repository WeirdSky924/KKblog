import re
from collections.abc import Callable, Iterable, Mapping
from datetime import date

from apps.core.ids import is_ulid
from apps.notifications.services.delivery import (
    NOTIFICATION_MARKDOWN_MAX_LENGTH,
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
_REPORT_REASON_LABELS = {
    "SPAM": "垃圾广告",
    "HARASSMENT": "辱骂骚扰",
    "ILLEGAL_DANGEROUS": "违法或危险内容",
    "PRIVACY": "隐私泄露",
    "IRRELEVANT": "无关内容",
    "OTHER": "其他",
}
_OPPORTUNITY_SOURCE_STATES = frozenset(
    {"NEVER", "HEALTHY", "DEGRADED", "STALE", "UNSUPPORTED"}
)
_OPPORTUNITY_RUN_STATES = frozenset(
    {"SUCCEEDED", "PARTIAL", "FAILED", "TRUNCATED", "CANCELLED"}
)
_OPPORTUNITY_STALL_REASONS = frozenset({"LEASE_EXPIRED", "SOURCE_TIMEOUT"})


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


def _empty(payload: Mapping[str, object]) -> None:
    _reject_unless(not payload)


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


def _opportunity_source_state(payload: Mapping[str, object]) -> None:
    source_name = payload["source_name"]
    previous = payload["previous_state"]
    current = payload["current_state"]
    failure_summary = payload["failure_summary"]
    _reject_unless(
        isinstance(source_name, str)
        and 1 <= len(source_name) <= 120
        and "<" not in source_name
        and ">" not in source_name
        and "://" not in source_name
        and previous in _OPPORTUNITY_SOURCE_STATES
        and current in _OPPORTUNITY_SOURCE_STATES
        and previous != current
        and isinstance(failure_summary, str)
        and len(failure_summary) <= 200
        and "<" not in failure_summary
        and ">" not in failure_summary
        and "://" not in failure_summary
        and (current in {"DEGRADED", "STALE", "UNSUPPORTED"}) == bool(failure_summary)
    )


def _opportunity_check_summary(payload: Mapping[str, object]) -> None:
    _reject_unless(payload["state"] in _OPPORTUNITY_RUN_STATES)
    for field in (
        "succeeded",
        "failed",
        "truncated",
        "skipped",
        "not_executed",
        "created",
        "changed",
        "missing",
        "job_failures",
    ):
        value = payload[field]
        _reject_unless(
            not isinstance(value, bool) and isinstance(value, int) and value >= 0
        )


def _opportunity_check_stalled(payload: Mapping[str, object]) -> None:
    run_id = payload["run_id"]
    source_name = payload["source_name"]
    source_position = payload["source_position"]
    attempt = payload["attempt"]
    max_duration = payload["max_duration_seconds"]
    _reject_unless(
        isinstance(run_id, str)
        and is_ulid(run_id)
        and isinstance(source_name, str)
        and 1 <= len(source_name) <= 120
        and "<" not in source_name
        and ">" not in source_name
        and "://" not in source_name
        and not isinstance(source_position, bool)
        and isinstance(source_position, int)
        and 1 <= source_position <= 5_000
        and payload["reason"] in _OPPORTUNITY_STALL_REASONS
        and not isinstance(attempt, bool)
        and isinstance(attempt, int)
        and 0 <= attempt <= 3
        and type(payload["final_failed"]) is bool
        and not isinstance(max_duration, bool)
        and isinstance(max_duration, int)
        and 0 <= max_duration <= 600
        and (
            payload["reason"] != "LEASE_EXPIRED" or (attempt >= 1 and max_duration == 0)
        )
        and (
            payload["reason"] != "SOURCE_TIMEOUT"
            or (attempt == 0 and not payload["final_failed"] and max_duration >= 1)
        )
    )


def _opportunity_source_title(payload: Mapping[str, object]) -> str:
    return (
        "招聘来源已恢复"
        if payload["current_state"] == "HEALTHY"
        else "招聘来源检查异常"
    )


def _opportunity_source_message(payload: Mapping[str, object]) -> str:
    if payload["current_state"] == "HEALTHY":
        return f"**{payload['source_name']}** 已恢复正常检查。"
    return (
        f"**{payload['source_name']}** 的检查状态已变为异常。\n\n"
        f"原因：{payload['failure_summary']}"
    )


def _opportunity_summary_message(payload: Mapping[str, object]) -> str:
    return "\n".join(
        (
            f"任务状态：**{payload['state']}**",
            "",
            f"- 成功来源：{payload['succeeded']}",
            f"- 失败来源：{payload['failed']}",
            f"- 截断来源：{payload['truncated']}",
            f"- 跳过来源：{payload['skipped']}",
            f"- 未执行来源：{payload['not_executed']}",
            f"- 新增岗位：{payload['created']}",
            f"- 字段变化：{payload['changed']}",
            f"- 来源列表缺失：{payload['missing']}",
            f"- 岗位链接失败：{payload['job_failures']}",
        )
    )


def _opportunity_stalled_title(payload: Mapping[str, object]) -> str:
    return (
        "招聘检查租约已过期"
        if payload["reason"] == "LEASE_EXPIRED"
        else "招聘来源执行超时"
    )


def _opportunity_stalled_message(payload: Mapping[str, object]) -> str:
    if payload["reason"] == "LEASE_EXPIRED":
        attempt = (
            f"第 {payload['attempt']} 次尝试" if payload["attempt"] else "当前尝试"
        )
        action = "已终止本次检查" if payload["final_failed"] else "将自动重试"
        return (
            f"招聘检查 **{payload['run_id']}** 的第 {payload['source_position']} 个来源"
            f"（**{payload['source_name']}**）{attempt}租约已过期，{action}。"
        )
    return (
        f"招聘检查 **{payload['run_id']}** 的第 {payload['source_position']} 个来源"
        f"（**{payload['source_name']}**）已超过配置的"
        f" {payload['max_duration_seconds']} 秒执行时限，系统已记录告警。"
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


def _generation_failed(payload: Mapping[str, object]) -> None:
    if not payload:
        return
    error_code = payload.get("error_code")
    _reject_unless(
        isinstance(error_code, str) and _ERROR_CODE.fullmatch(error_code) is not None
    )


_GENERATION_FAILURE_MESSAGES = {
    "agents.response_semantics_invalid.v1": (
        "模型返回内容未通过题库规则校验；本次失败调用未计入 token 额度。"
    ),
    "agents.response_schema_invalid.v1": (
        "模型返回内容未通过题库结构校验；本次失败调用未计入 token 额度。"
    ),
    "learning.question_schema_invalid.v1": (
        "生成内容未通过题库发布校验；本次失败调用未计入 token 额度。"
    ),
    "agents.quota_exhausted.v1": "模型额度不足，未继续调用。",
}


def _generation_failed_message(payload: Mapping[str, object]) -> str:
    error_code = payload.get("error_code")
    if isinstance(error_code, str):
        return _GENERATION_FAILURE_MESSAGES.get(
            error_code,
            f"题库生成未完成（{error_code}）；本次失败调用未计入 token 额度。",
        )
    return "题库生成出现系统错误，可稍后重试。"


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


def _broadcast_v2(payload: Mapping[str, object]) -> None:
    headline = payload["headline"]
    message = payload["message_markdown"]
    _reject_unless(
        isinstance(headline, str)
        and 1 <= len(headline) <= 100
        and "\n" not in headline
        and "\r" not in headline
        and _safe_reason(headline)
    )
    _reject_unless(
        isinstance(message, str)
        and bool(message.strip())
        and len(message) <= NOTIFICATION_MARKDOWN_MAX_LENGTH
        and "\x00" not in message
        and all(character.isprintable() or character in "\n\t" for character in message)
    )


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


def _report_context(payload: Mapping[str, object]) -> None:
    _reject_unless(
        is_ulid(payload["report_id"])
        and is_ulid(payload["target_comment_id"])
        and payload["reason"] in _REPORT_REASON_LABELS
        and _safe_reason(payload["description"])
    )


def _report_reviewed_v2(payload: Mapping[str, object]) -> None:
    _report_context(payload)
    _report_reviewed(payload)


def _report_finalized_v2(payload: Mapping[str, object]) -> None:
    _report_context(payload)
    _report_finalized(payload)
    basis_outcome = payload["basis_outcome"]
    outcome = payload["outcome"]
    recovery_status = payload["recovery_status"]
    _reject_unless(basis_outcome in {"UPHELD", "REJECTED"})
    _reject_unless(
        recovery_status in {"RESTORED", "FAILED"}
        if basis_outcome == "UPHELD" and outcome == "FINAL_REJECTED"
        else recovery_status == "NOT_REQUIRED"
    )


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


def _report_context_lines(payload: Mapping[str, object]) -> list[str]:
    return [
        f"举报编号：{payload['report_id']}",
        f"目标评论：{payload['target_comment_id']}",
        f"举报类型：{_REPORT_REASON_LABELS[payload['reason']]}",
        f"补充说明：{payload['description'] or '未填写'}",
    ]


def _report_review_title(payload: Mapping[str, object]) -> str:
    return "举报审核：成立" if payload["outcome"] == "UPHELD" else "举报审核：未成立"


def _report_review_message_v2(payload: Mapping[str, object]) -> str:
    upheld = payload["outcome"] == "UPHELD"
    lines = _report_context_lines(payload)
    lines.extend(
        (
            f"审核结果：{'举报成立' if upheld else '举报未成立'}",
            f"处理说明：{payload['decision_reason'] or '管理员未填写补充说明'}",
            (
                "内容处理：相关评论已删除，可在申诉后进行终局复审。"
                if upheld
                else "内容处理：相关评论保持原状态，举报人可发起申诉。"
            ),
        )
    )
    return "\n".join(lines)


def _report_final_title(payload: Mapping[str, object]) -> str:
    return (
        "举报终局：成立" if payload["outcome"] == "FINAL_UPHELD" else "举报终局：未成立"
    )


def _report_final_content_result(payload: Mapping[str, object]) -> str:
    if payload["recovery_status"] == "RESTORED":
        return "相关评论已恢复。"
    if payload["recovery_status"] == "FAILED":
        return "相关评论恢复失败，当前仍显示删除占位。"
    if payload["outcome"] == "FINAL_UPHELD":
        return "相关评论已删除。"
    return "相关评论保持原状态。"


def _report_final_message_v2(payload: Mapping[str, object]) -> str:
    lines = _report_context_lines(payload)
    lines.extend(
        (
            "初审结果："
            + ("举报成立" if payload["basis_outcome"] == "UPHELD" else "举报未成立"),
            "终局结果："
            + ("举报成立" if payload["outcome"] == "FINAL_UPHELD" else "举报未成立"),
            f"处理说明：{payload['decision_reason'] or '管理员未填写补充说明'}",
            f"内容处理：{_report_final_content_result(payload)}",
        )
    )
    return "\n".join(lines)


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
    *,
    markdown_fields: frozenset[str] = frozenset(),
    required_fields: frozenset[str] | None = None,
) -> NotificationTemplateSchema:
    return NotificationTemplateSchema(
        key=key,
        target_type=target_type,
        allowed_payload_fields=fields,
        required_payload_fields=(
            fields if required_fields is None else required_fields
        ),
        markdown_payload_fields=markdown_fields,
        payload_validator=validator,
    )


_BUILTINS = (
    (
        _schema(
            "opportunity.source_state_changed.v1",
            "opportunity_source",
            frozenset(
                {
                    "source_name",
                    "previous_state",
                    "current_state",
                    "failure_summary",
                }
            ),
            _opportunity_source_state,
        ),
        NotificationTemplateDefinition(
            "opportunity.source_state_changed.v1",
            _opportunity_source_title,
            _opportunity_source_message,
        ),
    ),
    (
        _schema(
            "opportunity.check_summary.v1",
            "opportunity_check_run",
            frozenset(
                {
                    "state",
                    "succeeded",
                    "failed",
                    "truncated",
                    "skipped",
                    "not_executed",
                    "created",
                    "changed",
                    "missing",
                    "job_failures",
                }
            ),
            _opportunity_check_summary,
        ),
        NotificationTemplateDefinition(
            "opportunity.check_summary.v1",
            "招聘检查结果",
            _opportunity_summary_message,
        ),
    ),
    (
        _schema(
            "opportunity.check_stalled.v1",
            "opportunity_check_run",
            frozenset(
                {
                    "run_id",
                    "source_name",
                    "source_position",
                    "reason",
                    "attempt",
                    "final_failed",
                    "max_duration_seconds",
                }
            ),
            _opportunity_check_stalled,
        ),
        NotificationTemplateDefinition(
            "opportunity.check_stalled.v1",
            _opportunity_stalled_title,
            _opportunity_stalled_message,
        ),
    ),
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
            "admin.broadcast.v2",
            "broadcast",
            frozenset({"headline", "message_markdown"}),
            _broadcast_v2,
            markdown_fields=frozenset({"message_markdown"}),
        ),
        NotificationTemplateDefinition(
            "admin.broadcast.v2",
            lambda payload: payload["headline"],
            lambda payload: payload["message_markdown"],
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
            "report.reviewed.v2",
            "report",
            frozenset(
                {
                    "report_id",
                    "target_comment_id",
                    "reason",
                    "description",
                    "outcome",
                    "decision_reason",
                }
            ),
            _report_reviewed_v2,
        ),
        NotificationTemplateDefinition(
            "report.reviewed.v2", _report_review_title, _report_review_message_v2
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
            "report.finalized.v2",
            "report",
            frozenset(
                {
                    "report_id",
                    "target_comment_id",
                    "reason",
                    "description",
                    "basis_outcome",
                    "outcome",
                    "decision_reason",
                    "recovery_status",
                }
            ),
            _report_finalized_v2,
        ),
        NotificationTemplateDefinition(
            "report.finalized.v2", _report_final_title, _report_final_message_v2
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
    (
        _schema(
            "learning.appeal_approved.v1",
            "learning_appeal",
            frozenset(),
            _empty,
        ),
        NotificationTemplateDefinition(
            "learning.appeal_approved.v1",
            "知识文档申诉已批准",
            lambda payload: "知识文档申诉已批准，文档已重新进入审核。",
        ),
    ),
    (
        _schema(
            "learning.appeal_rejected.v1",
            "learning_appeal",
            frozenset(),
            _empty,
        ),
        NotificationTemplateDefinition(
            "learning.appeal_rejected.v1",
            "知识文档申诉未通过",
            lambda payload: "知识文档申诉未通过，请查看处理结果。",
        ),
    ),
    (
        _schema(
            "learning.document_administration_changed.v1",
            "knowledge_document",
            frozenset({"action"}),
            _choice("action", frozenset({"HIDE", "RESTORE", "DELETE"})),
        ),
        NotificationTemplateDefinition(
            "learning.document_administration_changed.v1",
            "知识文档管理状态已更新",
            lambda payload: {
                "HIDE": "知识文档已被管理员暂时隐藏。",
                "RESTORE": "知识文档已被管理员恢复。",
                "DELETE": "知识文档已进入管理员删除冷静期。",
            }[payload["action"]],
        ),
    ),
    (
        _schema(
            "learning.question_bank_administration_changed.v1",
            "question_bank",
            frozenset({"action"}),
            _choice("action", frozenset({"HIDE", "RESTORE", "DELETE"})),
        ),
        NotificationTemplateDefinition(
            "learning.question_bank_administration_changed.v1",
            "题库管理状态已更新",
            lambda payload: {
                "HIDE": "题库已被管理员暂时隐藏。",
                "RESTORE": "题库已被管理员恢复。",
                "DELETE": "题库已进入管理员删除冷静期。",
            }[payload["action"]],
        ),
    ),
    (
        _schema(
            "learning.review_approved.v1",
            "knowledge_document",
            frozenset(),
            _empty,
        ),
        NotificationTemplateDefinition(
            "learning.review_approved.v1",
            "知识文档审核通过",
            lambda payload: "知识文档已通过审核，可以用于生成题库。",
        ),
    ),
    (
        _schema(
            "learning.review_rejected.v1",
            "knowledge_document",
            frozenset(),
            _empty,
        ),
        NotificationTemplateDefinition(
            "learning.review_rejected.v1",
            "知识文档未通过审核",
            lambda payload: "知识文档未通过审核，请查看安全原因后处理。",
        ),
    ),
    (
        _schema(
            "learning.review_failed.v1",
            "knowledge_document",
            frozenset(),
            _empty,
        ),
        NotificationTemplateDefinition(
            "learning.review_failed.v1",
            "知识文档审核失败",
            lambda payload: "知识文档审核出现系统错误，可稍后重试。",
        ),
    ),
    (
        _schema(
            "learning.generation_completed.v1",
            "question_bank_series",
            frozenset(),
            _empty,
        ),
        NotificationTemplateDefinition(
            "learning.generation_completed.v1",
            "题库生成完成",
            lambda payload: "题库已完整生成并公开。",
        ),
    ),
    (
        _schema(
            "learning.generation_partial.v1",
            "question_bank_series",
            frozenset(),
            _empty,
        ),
        NotificationTemplateDefinition(
            "learning.generation_partial.v1",
            "题库已按容量生成",
            lambda payload: "题库已生成并公开，部分知识点因单卷容量限制未覆盖。",
        ),
    ),
    (
        _schema(
            "learning.generation_failed.v1",
            "question_bank_series",
            frozenset({"error_code"}),
            _generation_failed,
            required_fields=frozenset(),
        ),
        NotificationTemplateDefinition(
            "learning.generation_failed.v1",
            "题库生成失败",
            _generation_failed_message,
        ),
    ),
    (
        _schema(
            "exchange.import_title_warning.v1",
            "article",
            frozenset(),
            _empty,
        ),
        NotificationTemplateDefinition(
            "exchange.import_title_warning.v1",
            "导入文章同标题提醒",
            lambda payload: "作者导入并发布了与其他作者同标题的文章，请复核。",
        ),
    ),
    (
        _schema(
            "exchange.export_completed.v1",
            "export_job",
            frozenset(),
            _empty,
        ),
        NotificationTemplateDefinition(
            "exchange.export_completed.v1",
            "导出已完成",
            lambda payload: "内容导出已完成，可在管理后台下载。",
        ),
    ),
    (
        _schema(
            "exchange.export_author_content.v1",
            "account",
            frozenset(),
            _empty,
        ),
        NotificationTemplateDefinition(
            "exchange.export_author_content.v1",
            "文章已由管理员导出",
            lambda payload: "管理员导出了你的文章内容。",
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
