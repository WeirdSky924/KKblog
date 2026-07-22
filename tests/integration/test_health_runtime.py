import pytest
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client
from redis import Redis


@pytest.mark.django_db(transaction=True)
def test_ready_reads_real_database_schema_and_redis() -> None:
    assert connection.vendor == "postgresql"
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1, current_database(), current_user")
        probe, database_name, username = cursor.fetchone()
    assert probe == 1
    assert database_name.startswith("test_kaj_test_")
    assert username == "kaj_test_runner"

    executor = MigrationExecutor(connection)
    assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []

    redis_client = Redis.from_url(settings.REDIS_URL)
    try:
        assert redis_client.ping() is True
    finally:
        redis_client.close()

    response = Client().get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
