from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from apps.core.errors import DomainError, ErrorCode
from apps.core.time.clock import require_aware


class CapacityState(StrEnum):
    NORMAL = "normal"
    WARN = "warn"
    NO_IMAGE = "no_image"
    READ_ONLY = "read_only"


class CapacityOperation(StrEnum):
    TEXT_CREATE = "text_create"
    IMAGE_CREATE = "image_create"
    DIAGNOSTIC_WRITE = "diagnostic_write"


@dataclass(frozen=True, slots=True)
class CapacitySample:
    total_bytes: int
    free_bytes: int
    observed_at: datetime

    def __post_init__(self) -> None:
        if (
            isinstance(self.total_bytes, bool)
            or not isinstance(self.total_bytes, int)
            or self.total_bytes <= 0
        ):
            raise ValueError("total_bytes must be a positive integer")
        if (
            isinstance(self.free_bytes, bool)
            or not isinstance(self.free_bytes, int)
            or not 0 <= self.free_bytes <= self.total_bytes
        ):
            raise ValueError("free_bytes must be between zero and total_bytes")
        try:
            require_aware(self.observed_at)
        except (AttributeError, TypeError, ValueError):
            raise ValueError("observed_at must be timezone-aware") from None
        object.__setattr__(self, "observed_at", self.observed_at.astimezone(UTC))


@dataclass(frozen=True, slots=True)
class CapacityDecision:
    state: CapacityState
    total_bytes: int
    free_bytes: int
    observed_at: datetime
    text_creation_allowed: bool
    image_creation_allowed: bool
    diagnostic_write_allowed: bool = True
    existing_content_read_allowed: bool = True


class CapacityPolicy:
    def evaluate(self, sample: CapacitySample) -> CapacityDecision:
        if not isinstance(sample, CapacitySample):
            raise TypeError("sample must be a CapacitySample")
        scaled_free = sample.free_bytes * 100
        if scaled_free < sample.total_bytes * 2:
            state = CapacityState.READ_ONLY
        elif scaled_free < sample.total_bytes * 5:
            state = CapacityState.NO_IMAGE
        elif scaled_free < sample.total_bytes * 10:
            state = CapacityState.WARN
        else:
            state = CapacityState.NORMAL
        return CapacityDecision(
            state=state,
            total_bytes=sample.total_bytes,
            free_bytes=sample.free_bytes,
            observed_at=sample.observed_at,
            text_creation_allowed=state != CapacityState.READ_ONLY,
            image_creation_allowed=state
            not in (CapacityState.NO_IMAGE, CapacityState.READ_ONLY),
        )


CapacitySampleSource = Callable[[], CapacitySample]


class CapacityGate:
    def __init__(
        self,
        sample_source: CapacitySampleSource,
        *,
        policy: CapacityPolicy | None = None,
    ) -> None:
        if not callable(sample_source):
            raise TypeError("sample_source must be callable")
        self._sample_source = sample_source
        self._policy = policy or CapacityPolicy()

    def evaluate(self) -> CapacityDecision:
        return self._policy.evaluate(self._sample_source())

    def require(self, operation: CapacityOperation) -> CapacityDecision:
        if not isinstance(operation, CapacityOperation):
            raise TypeError("operation must be a CapacityOperation")
        decision = self.evaluate()
        if operation == CapacityOperation.DIAGNOSTIC_WRITE:
            return decision
        if not decision.text_creation_allowed:
            raise DomainError(ErrorCode.CONTENT_CREATION_BLOCKED)
        if (
            operation == CapacityOperation.IMAGE_CREATE
            and not decision.image_creation_allowed
        ):
            raise DomainError(ErrorCode.IMAGE_CREATION_BLOCKED)
        return decision


def capacity_health_snapshot(gate: CapacityGate) -> CapacityDecision:
    if not isinstance(gate, CapacityGate):
        raise TypeError("gate must be a CapacityGate")
    return gate.evaluate()
