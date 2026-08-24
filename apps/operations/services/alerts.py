from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q

from apps.core.ids import new_uuid
from apps.core.time.clock import Clock, FrozenClock, SystemClock
from apps.operations.models import (
    AlertEmailStatus,
    OperationalAlert,
    OperationalAlertEmailWindow,
    OperationalAlertKind,
    OperationalAlertSeverity,
    TaskRun,
    TaskRunStatus,
)

from .errors import capture_runtime_error
from .tasks import RetryableTaskError

ALERT_EMAIL_FAILED = "operations.alert_email_failed.v1"
ALERT_EMAIL_DELIVERY_UNKNOWN = "operations.alert_email_delivery_unknown.v1"
ALERT_EMAIL_LEASE_SECONDS = 300
ALERT_EMAIL_RETRY_SECONDS = 60
CAPACITY_LOW_ERROR = "operations.capacity_low.v1"
SERVICE_UNAVAILABLE_ERROR = "operations.service_unavailable.v1"

_SOURCE_KEY = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_STATE_CODE = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")
_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*\Z")
_TRACE_CODE = re.compile(r"trc_[0-9a-hjkmnp-tv-z]{26}\Z")

_OPERATIONAL_TASK_NAMES = frozenset(
    {
        "config.runtime_tasks.smoke",
        "config.runtime_tasks.publish_outbox",
        "apps.operations.check_capacity",
        "apps.operations.check_service_health",
        "apps.analytics.expire_umami_data",
        "apps.operations.weekly_backup",
        "apps.operations.expire_backups",
        "apps.opportunities.schedule_daily_check",
        "apps.opportunities.recover_check_leases",
    }
)


class TaskFinalFailureObserved(RuntimeError):
    """A safe synthetic exception used to persist a task terminal failure."""


class AlertPersistenceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OperationalEmailMessage:
    delivery_id: str
    subject: str
    body: str


@dataclass(frozen=True, slots=True)
class AlertEmailBatchResult:
    sent: int
    skipped: int
    failed: int


AlertEmailSender = Callable[[OperationalEmailMessage], None]


def is_operational_task(task_name: str) -> bool:
    return task_name in _OPERATIONAL_TASK_NAMES


def _task_alert_fingerprint(run: TaskRun) -> str:
    material = json.dumps(
        {
            "kind": OperationalAlertKind.TASK_FINAL_FAILED,
            "run_id": run.run_id,
            "task_name": run.task_name,
            "error_code": run.last_error_code,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _capture_task_runtime_error(run: TaskRun, *, trace_code: str, clock: Clock):
    try:
        raise TaskFinalFailureObserved
    except TaskFinalFailureObserved as error:
        record = capture_runtime_error(
            error,
            trace_code=trace_code,
            error_code=run.last_error_code,
            context={
                "attempt": run.attempt,
                "business_object": run.business_object,
                "source": "task_run",
                "status": run.status,
                "task_name": run.task_name,
            },
            clock=clock,
        )
    if record is None:
        raise AlertPersistenceError("Task final failure could not be recorded")
    return record


def _hour_window(moment):
    return moment.replace(minute=0, second=0, microsecond=0)


def _ensure_email_window(alert: OperationalAlert, *, occurred_at) -> None:
    OperationalAlertEmailWindow.objects.get_or_create(
        alert=alert,
        window_started_at=_hour_window(occurred_at),
        defaults={"available_at": occurred_at},
    )


def _state_alert_fingerprint(
    *,
    kind: OperationalAlertKind,
    source_key: str,
    occurred_at: datetime,
) -> str:
    material = json.dumps(
        {
            "incident_started_at": occurred_at.isoformat(),
            "kind": kind,
            "source_key": source_key,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def record_operational_state_alert(
    *,
    kind: OperationalAlertKind,
    source_key: str,
    state_code: str,
    error_code: str,
    severity: OperationalAlertSeverity,
    trace_code: str,
    occurred_at: datetime,
) -> OperationalAlert:
    if kind not in {
        OperationalAlertKind.CAPACITY,
        OperationalAlertKind.SERVICE_HEALTH,
    }:
        raise AlertPersistenceError("Invalid operational state alert kind")
    if not isinstance(severity, OperationalAlertSeverity):
        raise AlertPersistenceError("Invalid operational alert severity")
    if (
        not isinstance(source_key, str)
        or not _SOURCE_KEY.fullmatch(source_key)
        or not isinstance(state_code, str)
        or not _STATE_CODE.fullmatch(state_code)
        or not isinstance(error_code, str)
        or not _ERROR_CODE.fullmatch(error_code)
        or not isinstance(trace_code, str)
        or not _TRACE_CODE.fullmatch(trace_code)
    ):
        raise AlertPersistenceError("Invalid operational state alert fact")
    FrozenClock(occurred_at)
    with transaction.atomic():
        alert = (
            OperationalAlert.objects.select_for_update()
            .filter(kind=kind, source_key=source_key, active=True)
            .first()
        )
        if alert is None:
            alert = OperationalAlert.objects.create(
                kind=kind,
                fingerprint=_state_alert_fingerprint(
                    kind=kind,
                    source_key=source_key,
                    occurred_at=occurred_at,
                ),
                source_key=source_key,
                state_code=state_code,
                error_code=error_code,
                trace_code=trace_code,
                severity=severity,
                first_seen_at=occurred_at,
                last_seen_at=occurred_at,
            )
        else:
            alert.state_code = state_code
            alert.error_code = error_code
            alert.trace_code = trace_code
            alert.severity = severity
            alert.occurrence_count += 1
            alert.last_seen_at = occurred_at
            alert.save(
                update_fields=(
                    "state_code",
                    "error_code",
                    "trace_code",
                    "severity",
                    "occurrence_count",
                    "last_seen_at",
                )
            )
        _ensure_email_window(alert, occurred_at=occurred_at)
        return alert


def resolve_operational_state_alert(
    *,
    kind: OperationalAlertKind,
    source_key: str,
    state_code: str,
    trace_code: str,
    occurred_at: datetime,
) -> OperationalAlert | None:
    if (
        kind not in {OperationalAlertKind.CAPACITY, OperationalAlertKind.SERVICE_HEALTH}
        or not isinstance(source_key, str)
        or not _SOURCE_KEY.fullmatch(source_key)
        or not isinstance(state_code, str)
        or not _STATE_CODE.fullmatch(state_code)
        or not isinstance(trace_code, str)
        or not _TRACE_CODE.fullmatch(trace_code)
    ):
        raise AlertPersistenceError("Invalid operational alert resolution")
    FrozenClock(occurred_at)
    with transaction.atomic():
        alert = (
            OperationalAlert.objects.select_for_update()
            .filter(kind=kind, source_key=source_key, active=True)
            .first()
        )
        if alert is None:
            return None
        alert.active = False
        alert.resolved_at = occurred_at
        alert.last_seen_at = occurred_at
        alert.state_code = state_code
        alert.trace_code = trace_code
        alert.save(
            update_fields=(
                "active",
                "resolved_at",
                "last_seen_at",
                "state_code",
                "trace_code",
            )
        )
        return alert


def record_task_final_failure_alert(
    run: TaskRun,
    *,
    trace_code: str,
    occurred_at: datetime,
) -> OperationalAlert:
    if not isinstance(run, TaskRun) or run.status != TaskRunStatus.FINAL_FAILED:
        raise AlertPersistenceError("Task run is not final failed")
    if run.attempt != 3 or not run.last_error_code or trace_code != run.trace_code:
        raise AlertPersistenceError("Task final failure fact is inconsistent")
    now = occurred_at
    runtime_error = _capture_task_runtime_error(
        run,
        trace_code=trace_code,
        clock=FrozenClock(now),
    )
    fingerprint = _task_alert_fingerprint(run)
    alert = (
        OperationalAlert.objects.select_for_update()
        .filter(fingerprint=fingerprint)
        .first()
    )
    if alert is None:
        alert = OperationalAlert.objects.create(
            kind=OperationalAlertKind.TASK_FINAL_FAILED,
            fingerprint=fingerprint,
            source_key=run.run_id,
            task_run=run,
            runtime_error=runtime_error,
            task_name=run.task_name,
            error_code=run.last_error_code,
            trace_code=trace_code,
            severity=OperationalAlertSeverity.CRITICAL,
            first_seen_at=now,
            last_seen_at=now,
        )
    else:
        if (
            alert.kind != OperationalAlertKind.TASK_FINAL_FAILED
            or alert.task_run_id != run.run_id
            or alert.error_code != run.last_error_code
        ):
            raise AlertPersistenceError("Alert fingerprint targets another failure")
        alert.runtime_error = runtime_error
        alert.trace_code = trace_code
        alert.active = True
        alert.resolved_at = None
        alert.occurrence_count += 1
        alert.last_seen_at = now
        alert.save(
            update_fields=(
                "runtime_error",
                "trace_code",
                "active",
                "resolved_at",
                "occurrence_count",
                "last_seen_at",
            )
        )
    if is_operational_task(run.task_name):
        _ensure_email_window(alert, occurred_at=now)
    return alert


def _message(window: OperationalAlertEmailWindow) -> OperationalEmailMessage:
    alert = window.alert
    if alert.kind == OperationalAlertKind.CAPACITY:
        body = (
            "磁盘容量监测触发告警。\n"
            f"监测源：{alert.source_key}\n"
            f"状态：{alert.state_code}\n"
            f"错误码：{alert.error_code}\n"
            f"追踪码：{alert.trace_code}\n"
        )
    elif alert.kind == OperationalAlertKind.SERVICE_HEALTH:
        body = (
            "服务健康监测触发告警。\n"
            f"监测源：{alert.source_key}\n"
            f"状态：{alert.state_code}\n"
            f"错误码：{alert.error_code}\n"
            f"追踪码：{alert.trace_code}\n"
        )
    else:
        body = (
            "后台任务已在三次尝试后最终失败。\n"
            f"任务：{alert.task_name}\n"
            f"错误码：{alert.error_code}\n"
            f"追踪码：{alert.trace_code}\n"
        )
    return OperationalEmailMessage(
        delivery_id=window.id,
        subject="Kaj 的小房间运维告警",
        body=body,
    )


def _recover_expired_email_claims(*, now) -> int:
    with transaction.atomic():
        expired = list(
            OperationalAlertEmailWindow.objects.select_for_update(skip_locked=True)
            .filter(
                status=AlertEmailStatus.SENDING,
                lease_expires_at__lte=now,
            )
            .select_related("alert")
        )
        for window in expired:
            window.status = AlertEmailStatus.UNKNOWN
            window.lease_token = None
            window.lease_expires_at = None
            window.last_error_code = ALERT_EMAIL_DELIVERY_UNKNOWN
            window.save(
                update_fields=(
                    "status",
                    "lease_token",
                    "lease_expires_at",
                    "last_error_code",
                    "updated_at",
                )
            )
    return len(expired)


def _claim_email(window_id: str, *, now):
    with transaction.atomic():
        window = (
            OperationalAlertEmailWindow.objects.select_for_update()
            .select_related("alert")
            .get(pk=window_id)
        )
        if window.status not in {AlertEmailStatus.PENDING, AlertEmailStatus.FAILED}:
            return None
        if window.available_at > now:
            return None
        window.status = AlertEmailStatus.SENDING
        window.attempts += 1
        window.lease_token = new_uuid()
        window.lease_expires_at = now + timedelta(seconds=ALERT_EMAIL_LEASE_SECONDS)
        window.last_error_code = ""
        window.save(
            update_fields=(
                "status",
                "attempts",
                "lease_token",
                "lease_expires_at",
                "last_error_code",
                "updated_at",
            )
        )
        return window.id, window.lease_token, _message(window)


def send_pending_operational_alert_emails(
    *,
    sender: AlertEmailSender,
    batch_size: int = 50,
    clock: Clock | None = None,
) -> AlertEmailBatchResult:
    if not callable(sender):
        raise TypeError("Operational email sender must be callable")
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= 200
    ):
        raise ValueError("Invalid alert email batch size")
    now = (clock or SystemClock()).now()
    unknown = _recover_expired_email_claims(now=now)
    window_ids = tuple(
        OperationalAlertEmailWindow.objects.filter(
            Q(status=AlertEmailStatus.PENDING) | Q(status=AlertEmailStatus.FAILED),
            available_at__lte=now,
        )
        .order_by("available_at", "id")
        .values_list("id", flat=True)[:batch_size]
    )
    sent = 0
    skipped = unknown
    failed = 0
    for window_id in window_ids:
        claim = _claim_email(window_id, now=now)
        if claim is None:
            skipped += 1
            continue
        claimed_id, lease_token, message = claim
        try:
            sender(message)
        except Exception:
            OperationalAlertEmailWindow.objects.filter(
                pk=claimed_id,
                status=AlertEmailStatus.SENDING,
                lease_token=lease_token,
            ).update(
                status=AlertEmailStatus.FAILED,
                available_at=now + timedelta(seconds=ALERT_EMAIL_RETRY_SECONDS),
                lease_token=None,
                lease_expires_at=None,
                last_error_code=ALERT_EMAIL_FAILED,
            )
            failed += 1
            continue
        updated = OperationalAlertEmailWindow.objects.filter(
            pk=claimed_id,
            status=AlertEmailStatus.SENDING,
            lease_token=lease_token,
        ).update(
            status=AlertEmailStatus.SENT,
            sent_at=now,
            lease_token=None,
            lease_expires_at=None,
            last_error_code="",
        )
        if updated:
            sent += 1
        else:
            skipped += 1
    if failed:
        raise RetryableTaskError(ALERT_EMAIL_FAILED)
    return AlertEmailBatchResult(sent=sent, skipped=skipped, failed=failed)
