import hashlib
from collections.abc import Callable
from uuid import UUID

from apps.core.events import EventEnvelope, consume_once
from apps.core.time.clock import Clock
from apps.notifications.services.delivery import (
    NotificationRejected,
    deliver_notification,
)
from apps.notifications.services.recipients import existing_notification_recipient_ids

CONSUMER_NAME = "notifications.opportunity-events.v1"
AdministratorIdProvider = Callable[[], UUID | None]

_FAILURE_LABELS = {
    "opportunities.request_dns_failed.v1": "域名解析失败",
    "opportunities.request_address_denied.v1": "目标地址不符合安全策略",
    "opportunities.request_host_denied.v1": "跳转目标不在允许域名内",
    "opportunities.request_timeout.v1": "请求超时",
    "opportunities.request_network_failed.v1": "网络请求失败",
    "opportunities.request_not_found.v1": "公开页面不存在或已移除",
    "opportunities.request_upstream_failed.v1": "来源服务暂时异常",
    "opportunities.request_status_failed.v1": "来源返回异常状态",
    "opportunities.robots_unavailable.v1": "robots.txt 无法安全确认",
    "opportunities.robots_invalid.v1": "robots.txt 无法解析",
    "opportunities.robots_denied.v1": "robots.txt 不允许自动访问",
    "opportunities.adapter_unavailable.v1": "来源适配器尚未提供",
    "opportunities.adapter_browser_unavailable.v1": "浏览器适配器尚未启用",
    "opportunities.adapter_result_invalid.v1": "来源页面结构无法识别",
    "opportunities.adapter_host_denied.v1": "岗位地址超出允许域名",
    "opportunities.adapter_duplicate_url.v1": "来源返回重复岗位地址",
    "opportunities.adapter_filter_unknown.v1": "岗位筛选信息不完整",
    "opportunities.collection_truncated.v1": "采集达到安全上限",
    "opportunities.collection_timeout.v1": "采集超过来源时长上限",
    "opportunities.response_too_large.v1": "来源响应超过安全大小上限",
}


def _recipient(provider: AdministratorIdProvider) -> tuple[UUID, ...]:
    if not callable(provider):
        raise TypeError("Administrator ID provider must be callable")
    administrator_id = provider()
    if not isinstance(administrator_id, UUID):
        raise NotificationRejected("Active administrator is unavailable")
    recipients = existing_notification_recipient_ids((administrator_id,))
    if recipients != (administrator_id,):
        raise NotificationRejected("Active administrator is unavailable")
    return recipients


def _source_delivery(envelope: EventEnvelope, recipients: tuple[UUID, ...]) -> None:
    payload = envelope.payload
    required = {"source_name", "previous_state", "current_state", "error_code"}
    if (
        envelope.aggregate_type != "opportunity_source"
        or set(payload) != required
        or payload["previous_state"] == payload["current_state"]
    ):
        raise NotificationRejected("Invalid opportunity source notification")
    error_code = payload["error_code"]
    if error_code:
        try:
            failure_summary = _FAILURE_LABELS[error_code]
        except KeyError:
            failure_summary = "来源检查未能安全完成"
    else:
        failure_summary = ""
    deliver_notification(
        template_key=envelope.event_type,
        recipient_ids=recipients,
        target_id=envelope.aggregate_id,
        payload={
            "source_name": payload["source_name"],
            "previous_state": payload["previous_state"],
            "current_state": payload["current_state"],
            "failure_summary": failure_summary,
        },
        dedupe_key=f"opportunity-source-state:{envelope.event_id}",
    )


def _summary_delivery(envelope: EventEnvelope, recipients: tuple[UUID, ...]) -> None:
    required = {
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
    if (
        envelope.aggregate_type != "opportunity_check_run"
        or set(envelope.payload) != required
    ):
        raise NotificationRejected("Invalid opportunity summary notification")
    deliver_notification(
        template_key=envelope.event_type,
        recipient_ids=recipients,
        target_id=envelope.aggregate_id,
        payload=dict(envelope.payload),
        dedupe_key=f"opportunity-check-summary:{envelope.aggregate_id}",
    )


def _stalled_delivery(envelope: EventEnvelope, recipients: tuple[UUID, ...]) -> None:
    if envelope.aggregate_type != "opportunity_check_run":
        raise NotificationRejected("Invalid opportunity stalled-check notification")
    payload = envelope.payload
    required = {
        "run_id",
        "source_name",
        "source_position",
        "reason",
        "attempt",
        "final_failed",
        "max_duration_seconds",
    }
    if set(payload) != required or payload["run_id"] != envelope.aggregate_id:
        raise NotificationRejected("Invalid opportunity stalled-check notification")
    source_name = payload["source_name"]
    if not isinstance(source_name, str):
        raise NotificationRejected("Invalid opportunity stalled-check notification")
    source_fingerprint = hashlib.sha256(source_name.encode("utf-8")).hexdigest()[:16]
    deliver_notification(
        template_key=envelope.event_type,
        recipient_ids=recipients,
        target_id=envelope.aggregate_id,
        payload=dict(payload),
        dedupe_key=(
            "opportunity-check-stalled:"
            f"{payload['run_id']}:{payload['source_position']}"
            f":{payload['reason']}:{payload['attempt']}:{source_fingerprint}"
        ),
    )


def _handle(
    envelope: EventEnvelope, *, administrator_id_provider: AdministratorIdProvider
) -> None:
    if not isinstance(envelope, EventEnvelope) or envelope.schema_version != 1:
        raise NotificationRejected("Invalid opportunity notification event")
    recipients = _recipient(administrator_id_provider)
    if envelope.event_type == "opportunity.source_state_changed.v1":
        _source_delivery(envelope, recipients)
        return
    if envelope.event_type == "opportunity.check_summary.v1":
        _summary_delivery(envelope, recipients)
        return
    if envelope.event_type == "opportunity.check_stalled.v1":
        _stalled_delivery(envelope, recipients)
        return
    raise NotificationRejected("Invalid opportunity notification event")


def consume_opportunity_notification(
    envelope: EventEnvelope,
    *,
    administrator_id_provider: AdministratorIdProvider,
    lease_seconds: int = 60,
    retry_delay_seconds: int = 60,
    clock: Clock | None = None,
):
    return consume_once(
        envelope,
        CONSUMER_NAME,
        lambda item: _handle(
            item,
            administrator_id_provider=administrator_id_provider,
        ),
        lease_seconds=lease_seconds,
        retry_delay_seconds=retry_delay_seconds,
        clock=clock,
    )


__all__ = ["consume_opportunity_notification"]
