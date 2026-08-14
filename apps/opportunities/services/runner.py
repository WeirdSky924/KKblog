from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from math import ceil
from time import monotonic as system_monotonic
from zoneinfo import ZoneInfo

from django.db import transaction

from apps.core.events import enqueue_event
from apps.core.time.clock import Clock, SystemClock

from ..checks import DomainRateLimiter, SafeHttpClient, SafeRequestError, get_adapter
from ..checks.robots import RobotsAwareHttpClient
from ..events import SOURCE_STATE_CHANGED
from ..models import (
    Opportunity,
    OpportunityCheck,
    OpportunityCheckRunSource,
    OpportunitySource,
    OpportunityStateTransition,
)
from .collection import (
    CollectionRejected,
    apply_adapter_result,
    record_collection_snapshot,
    validate_adapter_result,
)

ClientFactory = Callable[
    [OpportunitySource, frozenset[str], DomainRateLimiter], SafeHttpClient
]


@dataclass(frozen=True, slots=True)
class SourceRunResult:
    state: str
    source_check_id: str | None
    opportunity_checks: int
    created: int = 0
    changed: int = 0
    missing: int = 0
    failed_opportunity_checks: int = 0
    safe_error_code: str = ""


def _default_client_factory(source, allowed_hosts, rate_limiter):
    return SafeHttpClient(
        allowed_hosts=allowed_hosts,
        request_interval_seconds=max(2, source.request_interval_seconds),
        rate_limiter=rate_limiter,
    )


def _check_expiry(now):
    return now + timedelta(days=90)


def _check_state(result) -> str:
    if result.truncated:
        return OpportunityCheck.State.TRUNCATED
    if 200 <= result.status < 300:
        return OpportunityCheck.State.SUCCEEDED
    return OpportunityCheck.State.FAILED


def _safe_error_from_status(status: int) -> str:
    if status in (404, 410):
        return "opportunities.request_not_found.v1"
    if 500 <= status <= 599:
        return "opportunities.request_upstream_failed.v1"
    return "opportunities.request_status_failed.v1"


def _source_failure(source_id, *, checked_at, error_code):
    with transaction.atomic():
        source = OpportunitySource.objects.select_for_update().get(pk=source_id)
        previous_state = source.check_state
        same_failed_cycle = (
            source.last_checked_at is not None
            and source.last_checked_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
            == checked_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
            and bool(source.last_error_code)
        )
        if not same_failed_cycle:
            source.consecutive_failures += 1
        source.check_state = (
            OpportunitySource.CheckState.STALE
            if source.consecutive_failures >= 2
            else OpportunitySource.CheckState.DEGRADED
        )
        source.last_checked_at = checked_at
        source.last_error_code = error_code
        source.filter_options_stale = True
        source.save(
            update_fields=(
                "consecutive_failures",
                "check_state",
                "last_checked_at",
                "last_error_code",
                "filter_options_stale",
                "updated_at",
            )
        )
        if source.check_state != previous_state:
            enqueue_event(
                SOURCE_STATE_CHANGED,
                aggregate_type="opportunity_source",
                aggregate_id=str(source.id),
                payload={
                    "source_name": source.company_name,
                    "previous_state": previous_state,
                    "current_state": source.check_state,
                    "error_code": error_code,
                },
            )


def _source_success(source_id, *, checked_at, complete: bool):
    with transaction.atomic():
        source = OpportunitySource.objects.select_for_update().get(pk=source_id)
        previous_state = source.check_state
        has_confirmed_public_jobs = Opportunity.objects.filter(
            source_id=source_id,
            verification_status=Opportunity.VerificationStatus.CONFIRMED,
            publication_state=Opportunity.PublicationState.PUBLISHED,
        ).exists()
        error_code = "" if complete else "opportunities.collection_truncated.v1"
        source.check_state = (
            OpportunitySource.CheckState.HEALTHY
            if complete
            else OpportunitySource.CheckState.DEGRADED
        )
        source.consecutive_failures = 0
        source.last_success_at = checked_at
        source.last_checked_at = checked_at
        source.last_error_code = error_code
        source.filter_options_stale = not complete
        if complete or has_confirmed_public_jobs:
            source.publicly_visible = True
        source.save(
            update_fields=(
                "check_state",
                "consecutive_failures",
                "last_success_at",
                "last_checked_at",
                "last_error_code",
                "filter_options_stale",
                "publicly_visible",
                "updated_at",
            )
        )
        if source.check_state != previous_state and previous_state in (
            OpportunitySource.CheckState.DEGRADED,
            OpportunitySource.CheckState.STALE,
            OpportunitySource.CheckState.UNSUPPORTED,
        ):
            enqueue_event(
                SOURCE_STATE_CHANGED,
                aggregate_type="opportunity_source",
                aggregate_id=str(source.id),
                payload={
                    "source_name": source.company_name,
                    "previous_state": previous_state,
                    "current_state": source.check_state,
                    "error_code": error_code,
                },
            )


def _source_unsupported(source_id, *, checked_at, error_code):
    with transaction.atomic():
        source = OpportunitySource.objects.select_for_update().get(pk=source_id)
        previous_state = source.check_state
        source.check_state = OpportunitySource.CheckState.UNSUPPORTED
        source.consecutive_failures = 0
        source.last_checked_at = checked_at
        source.last_error_code = error_code
        source.filter_options_stale = True
        source.save(
            update_fields=(
                "check_state",
                "consecutive_failures",
                "last_checked_at",
                "last_error_code",
                "filter_options_stale",
                "updated_at",
            )
        )
        if source.check_state != previous_state:
            enqueue_event(
                SOURCE_STATE_CHANGED,
                aggregate_type="opportunity_source",
                aggregate_id=str(source.id),
                payload={
                    "source_name": source.company_name,
                    "previous_state": previous_state,
                    "current_state": source.check_state,
                    "error_code": error_code,
                },
            )


def _opportunity_result(
    row,
    *,
    success: bool,
    checked_at,
    source_check,
    error_code: str = "",
):
    with transaction.atomic():
        opportunity = Opportunity.objects.select_for_update().get(pk=row.id)
        previous_status = opportunity.verification_status
        if success:
            opportunity.consecutive_failures = 0
            opportunity.last_success_at = checked_at
            if (
                opportunity.verification_status
                == Opportunity.VerificationStatus.EXPIRED
            ):
                opportunity.verification_status = Opportunity.VerificationStatus.PENDING
            opportunity.last_error_code = ""
        else:
            same_failed_cycle = (
                opportunity.last_checked_at is not None
                and opportunity.last_checked_at.astimezone(
                    ZoneInfo("Asia/Shanghai")
                ).date()
                == checked_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
                and bool(opportunity.last_error_code)
            )
            if not same_failed_cycle:
                opportunity.consecutive_failures += 1
            if opportunity.consecutive_failures >= 2:
                opportunity.verification_status = Opportunity.VerificationStatus.EXPIRED
            opportunity.last_error_code = error_code
        opportunity.last_checked_at = checked_at
        opportunity.save(
            update_fields=(
                "consecutive_failures",
                "last_success_at",
                "last_checked_at",
                "last_error_code",
                "verification_status",
                "updated_at",
            )
        )
        if opportunity.verification_status != previous_status:
            OpportunityStateTransition.objects.create(
                opportunity=opportunity,
                source_check=source_check,
                previous_status=previous_status,
                current_status=opportunity.verification_status,
                reason_code=(
                    "opportunities.opportunity_recovered.v1" if success else error_code
                ),
                occurred_at=checked_at,
            )


def _listing_opportunity_success(source_id, *, checked_at, source_check) -> None:
    rows = Opportunity.objects.filter(source_id=source_id, list_missing=False)
    expired_ids = list(
        rows.filter(
            verification_status=Opportunity.VerificationStatus.EXPIRED
        ).values_list("id", flat=True)
    )
    rows.update(
        consecutive_failures=0,
        last_success_at=checked_at,
        last_checked_at=checked_at,
        last_error_code="",
        updated_at=checked_at,
    )
    if expired_ids:
        Opportunity.objects.filter(id__in=expired_ids).update(
            verification_status=Opportunity.VerificationStatus.PENDING,
            updated_at=checked_at,
        )
        OpportunityStateTransition.objects.bulk_create(
            [
                OpportunityStateTransition(
                    opportunity_id=identity,
                    source_check=source_check,
                    previous_status=Opportunity.VerificationStatus.EXPIRED,
                    current_status=Opportunity.VerificationStatus.PENDING,
                    reason_code="opportunities.opportunity_recovered.v1",
                    occurred_at=checked_at,
                )
                for identity in expired_ids
            ]
        )


def _create_failed_check(
    *,
    source,
    target_kind,
    trigger,
    task_run_id,
    started_at,
    error_code,
    opportunity=None,
):
    return OpportunityCheck.objects.create(
        source=source,
        opportunity=opportunity,
        task_run_id=task_run_id,
        target_kind=target_kind,
        trigger=trigger,
        state=OpportunityCheck.State.FAILED,
        safe_error_code=error_code,
        started_at=started_at,
        completed_at=started_at,
        expires_at=_check_expiry(started_at),
    )


def _create_skipped_filter_check(
    *,
    source,
    trigger,
    task_run_id,
    started_at,
    error_code,
):
    return OpportunityCheck.objects.create(
        source=source,
        task_run_id=task_run_id,
        target_kind=OpportunityCheck.TargetKind.FILTERS,
        trigger=trigger,
        state=OpportunityCheck.State.SKIPPED,
        safe_error_code=error_code,
        started_at=started_at,
        completed_at=started_at,
        expires_at=_check_expiry(started_at),
    )


def _record_http_check(
    *,
    source,
    opportunity,
    target_kind,
    trigger,
    task_run_id,
    started_at,
    response,
):
    state = _check_state(response)
    return OpportunityCheck.objects.create(
        source=source,
        opportunity=opportunity,
        task_run_id=task_run_id,
        target_kind=target_kind,
        trigger=trigger,
        state=state,
        http_status=response.status,
        final_url=response.final_url,
        page_title=response.title,
        safe_error_code=(
            "opportunities.response_too_large.v1"
            if response.truncated
            else (
                ""
                if state == OpportunityCheck.State.SUCCEEDED
                else _safe_error_from_status(response.status)
            )
        ),
        started_at=started_at,
        completed_at=started_at,
        expires_at=_check_expiry(started_at),
    )


def run_source_check(
    *,
    source_id,
    trigger: str,
    task_run_id: str,
    heartbeat: Callable[[], None],
    rate_limiter: DomainRateLimiter,
    client_factory: ClientFactory = _default_client_factory,
    clock: Clock | None = None,
    monotonic: Callable[[], float] = system_monotonic,
) -> SourceRunResult:
    if not callable(monotonic):
        raise TypeError("monotonic must be callable")
    active_clock = clock or SystemClock()
    started_at = active_clock.now()
    source = OpportunitySource.objects.prefetch_related("allowed_hosts").get(
        pk=source_id
    )
    if not source.enabled:
        return SourceRunResult(OpportunityCheckRunSource.State.SKIPPED, None, 0)
    deadline = monotonic() + source.max_duration_seconds

    def bounded_heartbeat() -> None:
        heartbeat()
        if monotonic() >= deadline:
            raise CollectionRejected("opportunities.collection_timeout.v1")

    allowed_hosts = frozenset(row.hostname for row in source.allowed_hosts.all())
    try:
        adapter = get_adapter(source.adapter_key)
    except LookupError:
        adapter = None
    browser_collection = bool(
        adapter is not None and getattr(adapter, "browser_collection_enabled", False)
    )
    robots_client = None
    if not browser_collection:
        client = client_factory(source, allowed_hosts, rate_limiter)
        robots_client = RobotsAwareHttpClient(
            client,
            respect_robots_txt=source.respect_robots_txt,
        )
    adapter_config = {
        **source.adapter_config,
        "_max_pages": source.max_pages,
        "_max_opportunities": source.max_opportunities,
        "_max_duration_seconds": max(1, ceil(deadline - monotonic())),
    }
    bounded_heartbeat()
    collected = None
    if browser_collection:
        try:
            collected = adapter.collect(
                source_url=source.official_url,
                config=adapter_config,
                client=robots_client,
                initial_response=None,
                heartbeat=bounded_heartbeat,
            )
        except (CollectionRejected, SafeRequestError) as error:
            source_check = _create_failed_check(
                source=source,
                target_kind=OpportunityCheck.TargetKind.SOURCE,
                trigger=trigger,
                task_run_id=task_run_id,
                started_at=started_at,
                error_code=error.error_code,
            )
            _source_failure(
                source.id,
                checked_at=started_at,
                error_code=error.error_code,
            )
            return SourceRunResult(
                OpportunityCheckRunSource.State.FAILED,
                source_check.id,
                0,
                safe_error_code=error.error_code,
            )
        source_check = OpportunityCheck.objects.create(
            source=source,
            target_kind=OpportunityCheck.TargetKind.SOURCE,
            trigger=trigger,
            task_run_id=task_run_id,
            state=OpportunityCheck.State.SUCCEEDED,
            http_status=200,
            started_at=started_at,
            completed_at=active_clock.now(),
            expires_at=_check_expiry(started_at),
        )
    else:
        try:
            source_probe = (
                adapter.source_probe_url(source.official_url)
                if adapter is not None and hasattr(adapter, "source_probe_url")
                else source.official_url
            )
            source_response = robots_client.get(source_probe)
        except SafeRequestError as error:
            check = _create_failed_check(
                source=source,
                target_kind=OpportunityCheck.TargetKind.SOURCE,
                trigger=trigger,
                task_run_id=task_run_id,
                started_at=started_at,
                error_code=error.error_code,
            )
            _source_failure(
                source.id,
                checked_at=started_at,
                error_code=error.error_code,
            )
            return SourceRunResult(
                OpportunityCheckRunSource.State.FAILED,
                check.id,
                0,
                safe_error_code=error.error_code,
            )
        source_check = _record_http_check(
            source=source,
            opportunity=None,
            target_kind=OpportunityCheck.TargetKind.SOURCE,
            trigger=trigger,
            task_run_id=task_run_id,
            started_at=started_at,
            response=source_response,
        )
    if source_check.state != OpportunityCheck.State.SUCCEEDED:
        _source_failure(
            source.id,
            checked_at=started_at,
            error_code=source_check.safe_error_code,
        )
        return SourceRunResult(
            OpportunityCheckRunSource.State.FAILED,
            source_check.id,
            0,
            safe_error_code=source_check.safe_error_code,
        )

    if adapter is None:
        error_code = "opportunities.adapter_unavailable.v1"
        _create_skipped_filter_check(
            source=source,
            trigger=trigger,
            task_run_id=task_run_id,
            started_at=started_at,
            error_code=error_code,
        )
        _source_unsupported(source.id, checked_at=started_at, error_code=error_code)
        return SourceRunResult(
            OpportunityCheckRunSource.State.SKIPPED,
            source_check.id,
            0,
            safe_error_code=error_code,
        )
    if adapter.browser_required and not getattr(
        adapter, "browser_collection_enabled", False
    ):
        error_code = "opportunities.adapter_browser_unavailable.v1"
        _create_skipped_filter_check(
            source=source,
            trigger=trigger,
            task_run_id=task_run_id,
            started_at=started_at,
            error_code=error_code,
        )
        _source_unsupported(source.id, checked_at=started_at, error_code=error_code)
        return SourceRunResult(
            OpportunityCheckRunSource.State.SKIPPED,
            source_check.id,
            0,
            safe_error_code=error_code,
        )
    try:
        if collected is None:
            collected = adapter.collect(
                source_url=source.official_url,
                config=adapter_config,
                client=robots_client,
                initial_response=source_response,
                heartbeat=bounded_heartbeat,
            )
        collected = validate_adapter_result(
            collected,
            source=source,
            allowed_hosts=allowed_hosts,
            observed_at=started_at,
        )
        applied = apply_adapter_result(
            source_id=source.id,
            result=collected,
            observed_at=started_at,
        )
    except (CollectionRejected, SafeRequestError) as error:
        error_code = error.error_code
        _create_failed_check(
            source=source,
            target_kind=OpportunityCheck.TargetKind.FILTERS,
            trigger=trigger,
            task_run_id=task_run_id,
            started_at=started_at,
            error_code=error_code,
        )
        _source_failure(source.id, checked_at=started_at, error_code=error_code)
        return SourceRunResult(
            OpportunityCheckRunSource.State.FAILED,
            source_check.id,
            0,
            safe_error_code=error_code,
        )

    if collected.truncated or not collected.complete:
        _source_success(source.id, checked_at=started_at, complete=False)
        run_state = OpportunityCheckRunSource.State.TRUNCATED
    else:
        _source_success(source.id, checked_at=started_at, complete=True)
        run_state = OpportunityCheckRunSource.State.SUCCEEDED
    filter_check = OpportunityCheck.objects.create(
        source=source,
        task_run_id=task_run_id,
        target_kind=OpportunityCheck.TargetKind.FILTERS,
        trigger=trigger,
        state=(
            OpportunityCheck.State.TRUNCATED
            if run_state == OpportunityCheckRunSource.State.TRUNCATED
            else OpportunityCheck.State.SUCCEEDED
        ),
        safe_error_code=(
            "opportunities.collection_truncated.v1"
            if run_state == OpportunityCheckRunSource.State.TRUNCATED
            else ""
        ),
        started_at=started_at,
        completed_at=started_at,
        expires_at=_check_expiry(started_at),
    )
    record_collection_snapshot(
        source=source,
        source_check=filter_check,
        result=collected,
        applied=applied,
        observed_at=started_at,
    )

    opportunity_checks = 0
    failed_opportunity_checks = 0
    if run_state == OpportunityCheckRunSource.State.SUCCEEDED:
        if adapter.authoritative_listing:
            _listing_opportunity_success(
                source.id,
                checked_at=started_at,
                source_check=filter_check,
            )
        else:
            opportunities = Opportunity.objects.filter(source=source).order_by("id")
        for opportunity in opportunities if not adapter.authoritative_listing else ():
            bounded_heartbeat()
            check_started_at = active_clock.now()
            try:
                if hasattr(adapter, "check_opportunity"):
                    response = adapter.check_opportunity(
                        source_url=source.official_url,
                        target_url=opportunity.target_url,
                        config={
                            **source.adapter_config,
                            "_max_pages": source.max_pages,
                            "_max_opportunities": source.max_opportunities,
                            "_max_duration_seconds": max(
                                1, ceil(deadline - monotonic())
                            ),
                        },
                        client=robots_client,
                    )
                else:
                    response = robots_client.get(opportunity.target_url)
            except SafeRequestError as error:
                check = _create_failed_check(
                    source=source,
                    opportunity=opportunity,
                    target_kind=OpportunityCheck.TargetKind.OPPORTUNITY,
                    trigger=trigger,
                    task_run_id=task_run_id,
                    started_at=check_started_at,
                    error_code=error.error_code,
                )
                _opportunity_result(
                    opportunity,
                    success=False,
                    checked_at=check_started_at,
                    source_check=check,
                    error_code=error.error_code,
                )
                failed_opportunity_checks += 1
            else:
                check = _record_http_check(
                    source=source,
                    opportunity=opportunity,
                    target_kind=OpportunityCheck.TargetKind.OPPORTUNITY,
                    trigger=trigger,
                    task_run_id=task_run_id,
                    started_at=check_started_at,
                    response=response,
                )
                _opportunity_result(
                    opportunity,
                    success=check.state == OpportunityCheck.State.SUCCEEDED,
                    checked_at=check_started_at,
                    source_check=check,
                    error_code=check.safe_error_code,
                )
                failed_opportunity_checks += int(
                    check.state != OpportunityCheck.State.SUCCEEDED
                )
            opportunity_checks += 1
    return SourceRunResult(
        run_state,
        source_check.id,
        opportunity_checks,
        created=applied.created,
        changed=applied.changed,
        missing=applied.missing,
        failed_opportunity_checks=failed_opportunity_checks,
        safe_error_code=(
            "opportunities.collection_truncated.v1"
            if run_state == OpportunityCheckRunSource.State.TRUNCATED
            else source_check.safe_error_code
        ),
    )


__all__ = ["ClientFactory", "SourceRunResult", "run_source_check"]
