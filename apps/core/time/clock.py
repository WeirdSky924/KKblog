from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


def require_aware(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Clock values must be timezone-aware")
    return moment


class Clock(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class FrozenClock:
    moment: datetime

    def __post_init__(self) -> None:
        require_aware(self.moment)

    def now(self) -> datetime:
        return self.moment
