from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.agents.contracts import AgentCommandError
from apps.agents.models import (
    AgentEndpoint,
    AgentEndpointCheck,
    AgentInvocation,
    AgentTokenAdjustment,
    AgentTokenLedger,
    AgentTokenReservation,
    AgentTokenResetOperation,
)
from apps.operations.public import record_audit_entry

from .common import (
    require_administrator,
    uuid_value,
    validate_idempotency_key,
    visible_text,
)


def _usage_date(now):
    if now is None:
        now = timezone.now()
    if not timezone.is_aware(now):
        raise AgentCommandError("agents.usage_time_invalid.v1", "用量时间不合法。")
    return timezone.localdate(now), now


def _locked_ledger_state(
    *, scope: str, usage_date, endpoint_id=None
) -> tuple[AgentTokenLedger, bool]:
    _ledger, created = AgentTokenLedger.objects.get_or_create(
        scope=scope,
        endpoint_id=endpoint_id,
        usage_date=usage_date,
    )
    return (
        AgentTokenLedger.objects.select_for_update().get(
            scope=scope,
            endpoint_id=endpoint_id,
            usage_date=usage_date,
        ),
        created,
    )


def _locked_ledger(*, scope: str, usage_date, endpoint_id=None) -> AgentTokenLedger:
    return _locked_ledger_state(
        scope=scope,
        endpoint_id=endpoint_id,
        usage_date=usage_date,
    )[0]


def _effective_tokens(ledger: AgentTokenLedger) -> int:
    adjustment = ledger.adjustments.aggregate(total=Sum("amount", default=0))["total"]
    return ledger.settled_tokens + adjustment


def _active_reserved_tokens(ledger: AgentTokenLedger, *, site: bool) -> int:
    relation = "site_ledger" if site else "endpoint_ledger"
    return AgentTokenReservation.objects.filter(
        **{relation: ledger},
        status=AgentTokenReservation.Status.ACTIVE,
    ).aggregate(total=Sum("requested_tokens", default=0))["total"]


def _existing_reservation(
    *, idempotency_key: str, owner_field: str, owner_id, requested_tokens: int
) -> AgentTokenReservation | None:
    existing = AgentTokenReservation.objects.filter(
        idempotency_key=idempotency_key
    ).first()
    if existing is None:
        return None
    if (
        getattr(existing, f"{owner_field}_id") != owner_id
        or existing.requested_tokens != requested_tokens
    ):
        raise AgentCommandError(
            "agents.idempotency_conflict.v1", "相同幂等标识已用于不同预留。"
        )
    return existing


def _reserve_locked(
    *,
    owner_field: str,
    owner,
    requested_tokens: int,
    stable_key: str,
    usage_date,
    lease_expires_at,
    maximum_tokens: int,
    concurrency_limit: int,
    site_daily_token_limit: int,
    endpoint_daily_token_limit: int,
) -> AgentTokenReservation:
    if not 1 <= requested_tokens <= maximum_tokens:
        raise AgentCommandError(
            "agents.reservation_invalid.v1", "预留 token 超过单次业务上限。"
        )
    site_ledger = _locked_ledger(
        scope=AgentTokenLedger.Scope.SITE,
        usage_date=usage_date,
    )
    endpoint_ledger = _locked_ledger(
        scope=AgentTokenLedger.Scope.ENDPOINT,
        endpoint_id=owner.endpoint_id,
        usage_date=usage_date,
    )
    site_used = _effective_tokens(site_ledger) + _active_reserved_tokens(
        site_ledger, site=True
    )
    endpoint_used = _effective_tokens(endpoint_ledger) + _active_reserved_tokens(
        endpoint_ledger, site=False
    )
    active_endpoint_runs = AgentTokenReservation.objects.filter(
        endpoint_ledger=endpoint_ledger,
        status=AgentTokenReservation.Status.ACTIVE,
    ).count()
    if active_endpoint_runs >= concurrency_limit:
        raise AgentCommandError(
            "agents.concurrency_exhausted.v1",
            "Endpoint 当前并发额度不足。",
        )
    if (
        site_used + requested_tokens > site_daily_token_limit
        or endpoint_used + requested_tokens > endpoint_daily_token_limit
    ):
        raise AgentCommandError(
            "agents.quota_exhausted.v1", "今日模型 token 额度不足。"
        )
    try:
        return AgentTokenReservation.objects.create(
            **{owner_field: owner},
            site_ledger=site_ledger,
            endpoint_ledger=endpoint_ledger,
            idempotency_key=stable_key,
            requested_tokens=requested_tokens,
            lease_expires_at=lease_expires_at,
        )
    except IntegrityError as exc:
        raise AgentCommandError(
            "agents.reservation_conflict.v1", "该运行已经预留额度。"
        ) from exc


def reserve_invocation_tokens(
    *,
    invocation_id,
    requested_tokens,
    idempotency_key,
    lease_expires_at,
    now=None,
) -> AgentTokenReservation:
    stable_key = validate_idempotency_key(idempotency_key)
    if isinstance(requested_tokens, bool) or not isinstance(requested_tokens, int):
        raise AgentCommandError("agents.reservation_invalid.v1", "预留 token 不合法。")
    usage_date, current = _usage_date(now)
    if not timezone.is_aware(lease_expires_at) or lease_expires_at <= current:
        raise AgentCommandError("agents.reservation_invalid.v1", "预留租约不合法。")
    existing = _existing_reservation(
        idempotency_key=stable_key,
        owner_field="invocation",
        owner_id=invocation_id,
        requested_tokens=requested_tokens,
    )
    if existing is not None:
        return existing

    with transaction.atomic():
        try:
            invocation = AgentInvocation.objects.select_for_update().get(
                pk=invocation_id
            )
        except AgentInvocation.DoesNotExist:
            raise AgentCommandError(
                "agents.invocation_not_found.v1", "AGENT 调用不存在。"
            ) from None
        return _reserve_locked(
            owner_field="invocation",
            owner=invocation,
            requested_tokens=requested_tokens,
            stable_key=stable_key,
            usage_date=usage_date,
            lease_expires_at=lease_expires_at,
            maximum_tokens=invocation.per_run_token_limit_snapshot,
            concurrency_limit=invocation.concurrency_limit_snapshot,
            site_daily_token_limit=invocation.site_daily_token_limit_snapshot,
            endpoint_daily_token_limit=invocation.endpoint_daily_token_limit_snapshot,
        )


def reserve_endpoint_check_tokens(
    *, check_id, idempotency_key, lease_expires_at, now=None
) -> AgentTokenReservation:
    stable_key = validate_idempotency_key(idempotency_key)
    usage_date, current = _usage_date(now)
    if not timezone.is_aware(lease_expires_at) or lease_expires_at <= current:
        raise AgentCommandError("agents.reservation_invalid.v1", "预留租约不合法。")
    try:
        normalized_id = str(check_id)
    except (TypeError, ValueError):
        raise AgentCommandError(
            "agents.endpoint_check_not_found.v1", "连接检查不存在。"
        ) from None
    existing = _existing_reservation(
        idempotency_key=stable_key,
        owner_field="endpoint_check",
        owner_id=normalized_id,
        requested_tokens=2_048,
    )
    if existing is not None:
        return existing
    with transaction.atomic():
        try:
            check = AgentEndpointCheck.objects.select_for_update().get(pk=normalized_id)
        except AgentEndpointCheck.DoesNotExist:
            raise AgentCommandError(
                "agents.endpoint_check_not_found.v1", "连接检查不存在。"
            ) from None
        if check.state != AgentEndpointCheck.State.RUNNING:
            raise AgentCommandError(
                "agents.endpoint_check_conflict.v1", "连接检查状态冲突。"
            )
        return _reserve_locked(
            owner_field="endpoint_check",
            owner=check,
            requested_tokens=check.token_budget,
            stable_key=stable_key,
            usage_date=usage_date,
            lease_expires_at=lease_expires_at,
            maximum_tokens=check.token_budget,
            concurrency_limit=check.concurrency_limit_snapshot,
            site_daily_token_limit=check.site_daily_token_limit_snapshot,
            endpoint_daily_token_limit=check.endpoint_daily_token_limit_snapshot,
        )


def settle_token_reservation(
    *, reservation_id, actual_tokens, status=AgentTokenReservation.Status.SETTLED
) -> AgentTokenReservation:
    if (
        isinstance(actual_tokens, bool)
        or not isinstance(actual_tokens, int)
        or actual_tokens < 0
    ):
        raise AgentCommandError("agents.settlement_invalid.v1", "结算 token 不合法。")
    if status not in {
        AgentTokenReservation.Status.SETTLED,
        AgentTokenReservation.Status.EXPIRED,
    }:
        raise AgentCommandError("agents.settlement_invalid.v1", "结算状态不合法。")
    with transaction.atomic():
        try:
            reservation = (
                AgentTokenReservation.objects.select_for_update()
                .select_related("site_ledger", "endpoint_ledger")
                .get(pk=reservation_id)
            )
        except AgentTokenReservation.DoesNotExist:
            raise AgentCommandError(
                "agents.reservation_not_found.v1", "token 预留不存在。"
            ) from None
        if reservation.status in {
            AgentTokenReservation.Status.SETTLED,
            AgentTokenReservation.Status.EXPIRED,
        }:
            if reservation.settled_tokens != actual_tokens:
                raise AgentCommandError(
                    "agents.settlement_conflict.v1", "token 预留已经按不同用量结算。"
                )
            return reservation
        if reservation.status != AgentTokenReservation.Status.ACTIVE:
            raise AgentCommandError(
                "agents.settlement_conflict.v1", "token 预留不能结算。"
            )
        if actual_tokens > reservation.requested_tokens:
            raise AgentCommandError(
                "agents.settlement_invalid.v1", "实际 token 超出预留上限。"
            )
        site_ledger = AgentTokenLedger.objects.select_for_update().get(
            pk=reservation.site_ledger_id
        )
        endpoint_ledger = AgentTokenLedger.objects.select_for_update().get(
            pk=reservation.endpoint_ledger_id
        )
        for ledger in (site_ledger, endpoint_ledger):
            ledger.settled_tokens += actual_tokens
            ledger.row_version += 1
            ledger.save(update_fields=("settled_tokens", "row_version", "updated_at"))
        reservation.status = status
        reservation.settled_tokens = actual_tokens
        reservation.save(update_fields=("status", "settled_tokens", "updated_at"))
    return reservation


@dataclass(frozen=True, slots=True)
class TokenReservationRecoveryResult:
    released_count: int
    conservative_count: int


def recover_expired_token_reservations(
    *, now=None, batch_size: int = 100
) -> TokenReservationRecoveryResult:
    current = now or timezone.now()
    if (
        not timezone.is_aware(current)
        or isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= 1000
    ):
        raise AgentCommandError("agents.recovery_invalid.v1", "恢复参数不合法。")
    released = 0
    conservative = 0
    with transaction.atomic():
        reservations = list(
            AgentTokenReservation.objects.select_for_update(skip_locked=True)
            .filter(
                status=AgentTokenReservation.Status.ACTIVE,
                lease_expires_at__lte=current,
            )
            .order_by("lease_expires_at", "id")[:batch_size]
        )
        for reservation in reservations:
            invocation = None
            endpoint_check = None
            if reservation.invocation_id is not None:
                invocation = AgentInvocation.objects.select_for_update().get(
                    pk=reservation.invocation_id
                )
                running = invocation.state == AgentInvocation.State.RUNNING
            else:
                endpoint_check = AgentEndpointCheck.objects.select_for_update().get(
                    pk=reservation.endpoint_check_id
                )
                running = endpoint_check.state == AgentEndpointCheck.State.RUNNING
            if running:
                settle_token_reservation(
                    reservation_id=reservation.id,
                    actual_tokens=0,
                    status=AgentTokenReservation.Status.EXPIRED,
                )
                # An expired/failed invocation does not consume the daily
                # quota. Keep the expired reservation as an audit fact, but
                # do not add its requested amount to either ledger.
            else:
                reservation.status = AgentTokenReservation.Status.RELEASED
                reservation.settled_tokens = 0
                reservation.save(
                    update_fields=("status", "settled_tokens", "updated_at")
                )
                released += 1
            if invocation is not None and invocation.state in {
                AgentInvocation.State.PENDING,
                AgentInvocation.State.RUNNING,
            }:
                invocation.state = AgentInvocation.State.FAILED
                invocation.completed_at = current
                invocation.safe_error_code = "agents.invocation_lease_expired.v1"
                invocation.save(
                    update_fields=(
                        "state",
                        "completed_at",
                        "safe_error_code",
                        "updated_at",
                    )
                )
            if endpoint_check is not None and endpoint_check.state in {
                AgentEndpointCheck.State.PENDING,
                AgentEndpointCheck.State.RUNNING,
            }:
                endpoint_check.state = AgentEndpointCheck.State.FAILED
                endpoint_check.started_at = endpoint_check.started_at or current
                endpoint_check.completed_at = current
                endpoint_check.usage_uncertain = running
                endpoint_check.safe_error_code = (
                    "agents.endpoint_check_lease_expired.v1"
                )
                endpoint_check.save(
                    update_fields=(
                        "state",
                        "started_at",
                        "completed_at",
                        "usage_uncertain",
                        "safe_error_code",
                        "updated_at",
                    )
                )
    return TokenReservationRecoveryResult(released, conservative)


def _adjust_to_zero(
    *,
    ledger: AgentTokenLedger,
    actor_id,
    reason: str,
    idempotency_key: str,
) -> AgentTokenAdjustment | None:
    before = _effective_tokens(ledger)
    if before == 0:
        return None
    adjustment = AgentTokenAdjustment.objects.create(
        ledger=ledger,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        amount=-before,
        before_effective_tokens=before,
        after_effective_tokens=0,
        reason=reason,
    )
    ledger.row_version += 1
    ledger.save(update_fields=("row_version", "updated_at"))
    return adjustment


def reset_token_usage(
    *,
    actor_id,
    scope,
    endpoint_id,
    reason,
    idempotency_key,
    trace_code,
    client_ip,
    expected_ledger_version=None,
    now=None,
) -> AgentTokenResetOperation:
    actor = require_administrator(actor_id)
    stable_key = validate_idempotency_key(idempotency_key)
    safe_reason = visible_text(reason, field="重置原因", maximum=255)
    usage_date, _ = _usage_date(now)
    if expected_ledger_version is not None and (
        isinstance(expected_ledger_version, bool)
        or not isinstance(expected_ledger_version, int)
        or expected_ledger_version < 0
    ):
        raise AgentCommandError(
            "agents.configuration_conflict.v1", "token 用量已被其他操作修改。"
        )
    if scope not in AgentTokenLedger.Scope.values:
        normalized_scope = str(scope).upper()
    else:
        normalized_scope = scope
    if normalized_scope not in AgentTokenLedger.Scope.values:
        raise AgentCommandError("agents.reset_scope_invalid.v1", "重置范围不合法。")
    stable_endpoint_id = None
    if normalized_scope == AgentTokenLedger.Scope.ENDPOINT:
        stable_endpoint_id = uuid_value(
            endpoint_id,
            code="agents.endpoint_not_found.v1",
            message="Endpoint 不存在。",
        )
    elif endpoint_id is not None:
        raise AgentCommandError(
            "agents.reset_scope_invalid.v1", "全站重置不能指定 Endpoint。"
        )

    existing = AgentTokenResetOperation.objects.filter(
        idempotency_key=stable_key
    ).first()
    if existing is not None:
        if (
            existing.scope != normalized_scope
            or existing.endpoint_id != stable_endpoint_id
            or existing.usage_date != usage_date
        ):
            raise AgentCommandError(
                "agents.idempotency_conflict.v1", "相同幂等标识已用于不同重置。"
            )
        return existing

    with transaction.atomic():
        site_ledger, site_created = _locked_ledger_state(
            scope=AgentTokenLedger.Scope.SITE, usage_date=usage_date
        )
        if normalized_scope == AgentTokenLedger.Scope.ENDPOINT:
            if not AgentEndpoint.objects.filter(pk=stable_endpoint_id).exists():
                raise AgentCommandError(
                    "agents.endpoint_not_found.v1", "Endpoint 不存在。"
                )
            endpoint_ledger, endpoint_created = _locked_ledger_state(
                scope=AgentTokenLedger.Scope.ENDPOINT,
                endpoint_id=stable_endpoint_id,
                usage_date=usage_date,
            )
            endpoint_ledgers = [endpoint_ledger]
            target_ledger = endpoint_ledger
            target_created = endpoint_created
            before = _effective_tokens(endpoint_ledgers[0])
            active_count = AgentTokenReservation.objects.filter(
                endpoint_ledger=endpoint_ledgers[0],
                status=AgentTokenReservation.Status.ACTIVE,
            ).count()
        else:
            endpoint_ledgers = list(
                AgentTokenLedger.objects.select_for_update().filter(
                    scope=AgentTokenLedger.Scope.ENDPOINT,
                    usage_date=usage_date,
                )
            )
            before = _effective_tokens(site_ledger)
            target_ledger = site_ledger
            target_created = site_created
            active_count = AgentTokenReservation.objects.filter(
                site_ledger=site_ledger,
                status=AgentTokenReservation.Status.ACTIVE,
            ).count()
        if expected_ledger_version is not None and (
            (expected_ledger_version == 0 and not target_created)
            or (
                expected_ledger_version > 0
                and target_ledger.row_version != expected_ledger_version
            )
        ):
            raise AgentCommandError(
                "agents.configuration_conflict.v1", "token 用量已被其他操作修改。"
            )
        adjustments = []
        for ledger in endpoint_ledgers:
            adjustment = _adjust_to_zero(
                ledger=ledger,
                actor_id=actor,
                reason=safe_reason,
                idempotency_key=f"{stable_key}:endpoint:{ledger.endpoint_id}",
            )
            if adjustment is not None:
                adjustments.append(adjustment)
        site_amount = (
            before
            if normalized_scope == AgentTokenLedger.Scope.ENDPOINT
            else _effective_tokens(site_ledger)
        )
        if site_amount:
            site_adjustment = AgentTokenAdjustment.objects.create(
                ledger=site_ledger,
                actor_id=actor,
                idempotency_key=f"{stable_key}:site",
                amount=-site_amount,
                before_effective_tokens=_effective_tokens(site_ledger),
                after_effective_tokens=_effective_tokens(site_ledger) - site_amount,
                reason=safe_reason,
            )
            site_ledger.row_version += 1
            site_ledger.save(update_fields=("row_version", "updated_at"))
            adjustments.append(site_adjustment)
        operation = AgentTokenResetOperation.objects.create(
            actor_id=actor,
            scope=normalized_scope,
            endpoint_id=stable_endpoint_id,
            usage_date=usage_date,
            idempotency_key=stable_key,
            reason=safe_reason,
            before_effective_tokens=before,
            after_effective_tokens=0,
            active_reservation_count=active_count,
            adjustment_count=len(adjustments),
        )
        record_audit_entry(
            action="agents.token_usage.reset",
            actor_id=actor,
            target_id=operation.id,
            trace_code=trace_code,
            client_ip=client_ip,
            before={"before_units": before},
            after={
                "scope": normalized_scope,
                "endpoint_id": str(stable_endpoint_id) if stable_endpoint_id else None,
                "after_units": 0,
                "active_reservation_count": active_count,
                "adjustment_count": len(adjustments),
            },
            summary="Reset agent token usage",
        )
    return operation


__all__ = [
    "TokenReservationRecoveryResult",
    "recover_expired_token_reservations",
    "reserve_endpoint_check_tokens",
    "reserve_invocation_tokens",
    "reset_token_usage",
    "settle_token_reservation",
]
