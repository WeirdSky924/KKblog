from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from apps.analytics.services.retention import PostgresUmamiRetentionStore
from config.environment import load_isolated_umami_database_url

pytestmark = pytest.mark.integration


def _database_url() -> str:
    value = load_isolated_umami_database_url(os.environ)
    if value is None:
        pytest.skip("KAJ_TEST_UMAMI_DATABASE_URL is not configured")
    return value


def _create_fixed_v2190_subset(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "DROP TABLE IF EXISTS event_data, revenue, website_event, "
            "session_data, session"
        )
        cursor.execute(
            """
            CREATE TABLE session (
                session_id uuid PRIMARY KEY,
                created_at timestamptz
            );
            CREATE TABLE website_event (
                event_id uuid PRIMARY KEY,
                session_id uuid NOT NULL,
                created_at timestamptz
            );
            CREATE TABLE event_data (
                event_data_id uuid PRIMARY KEY,
                website_event_id uuid NOT NULL,
                created_at timestamptz
            );
            CREATE TABLE session_data (
                session_data_id uuid PRIMARY KEY,
                session_id uuid NOT NULL,
                created_at timestamptz
            );
            CREATE TABLE revenue (
                revenue_id uuid PRIMARY KEY,
                event_id uuid NOT NULL,
                session_id uuid NOT NULL,
                created_at timestamptz
            );
            """
        )
    connection.commit()


def test_postgres_retention_matches_umami_v2190_boundary_and_delete_order() -> None:
    database_url = _database_url()
    now = datetime(2026, 7, 27, 20, 15, tzinfo=UTC)
    cutoff = now - timedelta(days=30)
    old_session, boundary_session = uuid4(), uuid4()
    old_event, boundary_event = uuid4(), uuid4()

    with psycopg.connect(database_url) as connection:
        _create_fixed_v2190_subset(connection)
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO session (session_id, created_at) VALUES (%s, %s)",
                (
                    (old_session, cutoff - timedelta(microseconds=1)),
                    (boundary_session, cutoff),
                ),
            )
            cursor.executemany(
                "INSERT INTO website_event (event_id, session_id, created_at) VALUES (%s, %s, %s)",
                (
                    (old_event, old_session, cutoff - timedelta(microseconds=1)),
                    (boundary_event, boundary_session, cutoff),
                ),
            )
            cursor.executemany(
                "INSERT INTO event_data VALUES (%s, %s, %s)",
                ((uuid4(), old_event, now), (uuid4(), boundary_event, cutoff)),
            )
            cursor.executemany(
                "INSERT INTO revenue VALUES (%s, %s, %s, %s)",
                (
                    (uuid4(), old_event, old_session, now),
                    (uuid4(), boundary_event, boundary_session, cutoff),
                ),
            )
            cursor.executemany(
                "INSERT INTO session_data VALUES (%s, %s, %s)",
                (
                    (uuid4(), old_session, cutoff - timedelta(microseconds=1)),
                    (uuid4(), boundary_session, cutoff),
                ),
            )

    store = PostgresUmamiRetentionStore(database_url)
    first = store.delete_before(cutoff)
    second = store.delete_before(cutoff)

    assert first.event_data == 1
    assert first.revenue == 1
    assert first.website_events == 1
    assert first.session_data == 1
    assert first.sessions == 1
    assert second.total == 0
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            for table in (
                "event_data",
                "revenue",
                "website_event",
                "session_data",
                "session",
            ):
                cursor.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
                )
                assert cursor.fetchone()[0] == 1
