from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .clock import require_aware

SHANGHAI = ZoneInfo("Asia/Shanghai")


def to_shanghai(moment: datetime) -> datetime:
    return require_aware(moment).astimezone(SHANGHAI)


def shanghai_business_date(moment: datetime) -> date:
    return to_shanghai(moment).date()


def shanghai_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    start_local = datetime.combine(day, time.min, tzinfo=SHANGHAI)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)
