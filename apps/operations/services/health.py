from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from redis import Redis


class ReadinessUnavailable(RuntimeError):
    """Safe readiness failure with no dependency details."""

    def __init__(self) -> None:
        super().__init__("runtime is not ready")


def _check_database() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        if cursor.fetchone() != (1,):
            raise RuntimeError("database readiness probe returned an invalid result")


def _check_migrations() -> None:
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    if executor.migration_plan(targets):
        raise RuntimeError("database schema is not current")


def _check_redis() -> None:
    client = Redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        if client.ping() is not True:
            raise RuntimeError("cache readiness probe returned an invalid result")
    finally:
        client.close()


@dataclass(frozen=True, slots=True)
class ReadinessChecks:
    database: Callable[[], None]
    migrations: Callable[[], None]
    cache: Callable[[], None]


def check_readiness(checks: ReadinessChecks | None = None) -> None:
    active_checks = checks or ReadinessChecks(
        database=_check_database,
        migrations=_check_migrations,
        cache=_check_redis,
    )
    try:
        active_checks.database()
        active_checks.migrations()
        active_checks.cache()
    except Exception:
        raise ReadinessUnavailable() from None


def application_is_ready() -> bool:
    try:
        check_readiness()
    except ReadinessUnavailable:
        return False
    return True
