from dataclasses import dataclass

from django.db import transaction

from apps.core.time.clock import Clock, SystemClock

from ..models import OpportunityCheck, OpportunityCollectionSnapshot


@dataclass(frozen=True, slots=True)
class RetentionResult:
    snapshots: int
    checks: int


def cleanup_expired_check_history(
    *,
    batch_size: int = 500,
    clock: Clock | None = None,
) -> RetentionResult:
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= 1000
    ):
        raise ValueError("Invalid opportunity retention batch size")
    now = (clock or SystemClock()).now()
    with transaction.atomic():
        snapshot_ids = list(
            OpportunityCollectionSnapshot.objects.filter(expires_at__lte=now)
            .order_by("expires_at", "id")
            .values_list("id", flat=True)[:batch_size]
        )
        snapshots = OpportunityCollectionSnapshot.objects.filter(
            id__in=snapshot_ids
        ).delete()[0]
        check_ids = list(
            OpportunityCheck.objects.filter(expires_at__lte=now)
            .order_by("expires_at", "id")
            .values_list("id", flat=True)[:batch_size]
        )
        checks = OpportunityCheck.objects.filter(id__in=check_ids).delete()[0]
    return RetentionResult(snapshots=snapshots, checks=checks)


__all__ = ["RetentionResult", "cleanup_expired_check_history"]
