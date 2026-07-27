from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

import psycopg

from apps.core.time.clock import Clock, SystemClock

UMAMI_RETENTION_DAYS = 30
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_RETENTION_LOCK_ID = 7_041_255_114_457_007
_REQUIRED_COLUMNS = {
    "event_data": frozenset({"created_at", "website_event_id"}),
    "revenue": frozenset({"created_at", "event_id", "session_id"}),
    "session": frozenset({"created_at", "session_id"}),
    "session_data": frozenset({"created_at", "session_id"}),
    "website_event": frozenset({"created_at", "event_id", "session_id"}),
}


class UmamiRetentionError(RuntimeError):
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


@dataclass(frozen=True, slots=True)
class UmamiRetentionCounts:
    event_data: int = 0
    revenue: int = 0
    website_events: int = 0
    session_data: int = 0
    sessions: int = 0

    @property
    def total(self) -> int:
        return (
            self.event_data
            + self.revenue
            + self.website_events
            + self.session_data
            + self.sessions
        )


@dataclass(frozen=True, slots=True)
class UmamiRetentionResult:
    cutoff: datetime
    counts: UmamiRetentionCounts


class UmamiRetentionStore(Protocol):
    def delete_before(self, cutoff: datetime) -> UmamiRetentionCounts: ...


def _validated_database_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port or 5432
    except (TypeError, ValueError):
        raise UmamiRetentionError(
            "analytics.database_configuration_invalid.v1"
        ) from None
    database_name = unquote(parsed.path.lstrip("/"))
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or not parsed.hostname
        or not parsed.username
        or not database_name
        or not 1 <= port <= 65_535
        or parsed.fragment
    ):
        raise UmamiRetentionError("analytics.database_configuration_invalid.v1")
    return value


def _schema_is_supported(rows: list[tuple[str, str]]) -> bool:
    actual: dict[str, set[str]] = {}
    for table_name, column_name in rows:
        actual.setdefault(table_name, set()).add(column_name)
    return all(
        columns <= actual.get(table, set())
        for table, columns in _REQUIRED_COLUMNS.items()
    )


@dataclass(frozen=True, slots=True)
class PostgresUmamiRetentionStore:
    database_url: str = field(repr=False)
    connector: Callable[..., object] = field(default=psycopg.connect, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "database_url",
            _validated_database_url(self.database_url),
        )
        if not callable(self.connector):
            raise TypeError("connector must be callable")

    def delete_before(self, cutoff: datetime) -> UmamiRetentionCounts:
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("cutoff must be timezone-aware")
        try:
            with self.connector(
                self.database_url,
                autocommit=False,
                connect_timeout=10,
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                    cursor.execute("SET LOCAL lock_timeout = '5s'")
                    cursor.execute("SET LOCAL statement_timeout = '5min'")
                    cursor.execute(
                        "SELECT pg_try_advisory_xact_lock(%s)",
                        (_RETENTION_LOCK_ID,),
                    )
                    lock_row = cursor.fetchone()
                    if not lock_row or lock_row[0] is not True:
                        raise UmamiRetentionError("analytics.retention_busy.v1")
                    cursor.execute(
                        """
                        SELECT table_name, column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = ANY(%s)
                        """,
                        (list(_REQUIRED_COLUMNS),),
                    )
                    if not _schema_is_supported(cursor.fetchall()):
                        raise UmamiRetentionError(
                            "analytics.umami_schema_unsupported.v1"
                        )

                    cursor.execute(
                        """
                        DELETE FROM event_data AS data
                        WHERE data.created_at < %s
                           OR EXISTS (
                               SELECT 1 FROM website_event AS event
                               WHERE event.event_id = data.website_event_id
                                 AND event.created_at < %s
                           )
                        """,
                        (cutoff, cutoff),
                    )
                    event_data = cursor.rowcount
                    cursor.execute(
                        """
                        DELETE FROM revenue AS item
                        WHERE item.created_at < %s
                           OR EXISTS (
                               SELECT 1 FROM website_event AS event
                               WHERE event.event_id = item.event_id
                                 AND event.created_at < %s
                           )
                        """,
                        (cutoff, cutoff),
                    )
                    revenue = cursor.rowcount
                    cursor.execute(
                        "DELETE FROM website_event WHERE created_at < %s",
                        (cutoff,),
                    )
                    website_events = cursor.rowcount
                    cursor.execute(
                        "DELETE FROM session_data WHERE created_at < %s",
                        (cutoff,),
                    )
                    session_data = cursor.rowcount
                    cursor.execute(
                        """
                        DELETE FROM session AS item
                        WHERE item.created_at < %s
                          AND NOT EXISTS (
                              SELECT 1 FROM website_event
                              WHERE session_id = item.session_id
                          )
                          AND NOT EXISTS (
                              SELECT 1 FROM session_data
                              WHERE session_id = item.session_id
                          )
                          AND NOT EXISTS (
                              SELECT 1 FROM revenue
                              WHERE session_id = item.session_id
                          )
                        """,
                        (cutoff,),
                    )
                    sessions = cursor.rowcount
        except UmamiRetentionError:
            raise
        except (OSError, psycopg.Error):
            raise UmamiRetentionError(
                "analytics.retention_database_unavailable.v1"
            ) from None
        return UmamiRetentionCounts(
            event_data=event_data,
            revenue=revenue,
            website_events=website_events,
            session_data=session_data,
            sessions=sessions,
        )


def shanghai_retention_date(*, clock: Clock | None = None):
    now = (clock or SystemClock()).now()
    return now.astimezone(_SHANGHAI).date()


def expire_umami_data(
    *,
    store: UmamiRetentionStore,
    clock: Clock | None = None,
) -> UmamiRetentionResult:
    if not callable(getattr(store, "delete_before", None)):
        raise TypeError("store must implement delete_before")
    now = (clock or SystemClock()).now()
    cutoff = now - timedelta(days=UMAMI_RETENTION_DAYS)
    counts = store.delete_before(cutoff)
    if not isinstance(counts, UmamiRetentionCounts):
        raise TypeError("retention store returned an invalid result")
    return UmamiRetentionResult(cutoff=cutoff, counts=counts)
