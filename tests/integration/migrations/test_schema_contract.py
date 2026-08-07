import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from psycopg import sql

pytestmark = pytest.mark.django_db(transaction=True)

REQUIRED_CONSTRAINTS = {
    "account_role_unique",
    "login_session_positive_lifetime",
    "invite_positive_lifetime",
    "invite_redemption_pair",
    "article_deletion_times_shape",
    "article_schedule_shape",
    "article_working_revision_same_article_fk",
    "article_published_revision_same_article_fk",
    "article_scheduled_revision_same_article_fk",
    "article_revision_sequence_unique",
    "article_revision_title_nonempty",
    "article_revision_body_shape",
    "article_revision_based_on_same_article_fk",
    "article_revision_restore_source_same_article_fk",
    "content_revision_tag_unique",
    "content_article_tag_unique",
    "media_asset_size_range",
    "media_binding_target_slot_unique",
    "discussion_thread_target_unique",
    "comment_tree_guard",
    "comment_visible_at_order",
    "moderation_report_reporter_target_unique",
    "moderation_report_appeal_report_id_key",
    "notification_receipt_unique",
    "operations_task_idempotency_unique",
    "navigation_node_depth_range",
    "discovery_reading_bookmark_account_article_unique",
    "discovery_reading_bookmark_progress_range",
    "discovery_article_like_account_article_unique",
    "comment_pin_thread_unique",
    "comment_pin_comment_unique",
}

REQUIRED_INDEXES = {
    "account_email_ci_unique",
    "account_nickname_casefold_unique",
    "one_administrator_role",
    "ip_block_active_addr_uniq",
    "login_session_active_idx",
    "article_author_updated_idx",
    "article_schedule_due_idx",
    "article_purge_due_idx",
    "article_rev_title_trgm_gin",
    "content_tag_live_name_unique",
    "content_tag_article_idx",
    "comment_top_created_idx",
    "comment_reply_created_idx",
    "comment_top_hot_idx",
    "comment_buffer_due_idx",
    "moderation_report_queue_idx",
    "notification_unread_idx",
    "operations_task_ready_idx",
    "operations_task_lease_idx",
    "exchange_export_active_unique",
    "exchange_export_state_idx",
    "exchange_export_expiry_idx",
    "navigation_parent_order_idx",
    "navigation_public_tree_idx",
    "discovery_readmark_updated_idx",
    "discovery_like_count_idx",
}


def _admin_connection(database_url: str):
    parsed = urlsplit(database_url)
    return psycopg.connect(
        host=parsed.hostname,
        port=parsed.port,
        user=parsed.username,
        dbname="postgres",
        autocommit=True,
    )


def _database_url(database_url: str, database_name: str) -> str:
    parsed = urlsplit(database_url)
    return urlunsplit(parsed._replace(path=f"/{database_name}"))


def test_empty_postgresql_database_migrates_to_every_leaf() -> None:
    source_url = os.environ["KAJ_TEST_DATABASE_URL"]
    database_name = f"kaj_test_p12_empty_{uuid4().hex[:12]}"
    target_url = _database_url(source_url, database_name)
    with _admin_connection(source_url) as admin:
        admin.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
        )
    try:
        environment = os.environ.copy()
        environment.update(
            DJANGO_SETTINGS_MODULE="config.settings.test",
            KAJ_TEST_DATABASE_URL=target_url,
        )
        result = subprocess.run(
            [sys.executable, "manage.py", "migrate", "--noinput"],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        with psycopg.connect(target_url) as migrated:
            applied = migrated.execute(
                "SELECT app, name FROM django_migrations"
            ).fetchall()
            extensions = {
                row[0] for row in migrated.execute("SELECT extname FROM pg_extension")
            }
            tables = {
                row[0]
                for row in migrated.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                )
            }
        leaves = set(MigrationExecutor(connection).loader.graph.leaf_nodes())
        assert leaves <= set(applied)
        assert "pg_trgm" in extensions
        assert {
            "account",
            "article",
            "comment",
            "comment_pin",
            "discovery_article_like",
            "operations_task_run",
        } <= tables
    finally:
        with _admin_connection(source_url) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database_name,),
            )
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(
                    sql.Identifier(database_name)
                )
            )


def test_current_schema_is_at_every_migration_leaf() -> None:
    executor = MigrationExecutor(connection)
    leaves = set(executor.loader.graph.leaf_nodes())
    applied = set(executor.recorder.applied_migrations())

    assert leaves <= applied
    assert executor.migration_plan(leaves) == []


def test_required_constraints_and_query_indexes_exist() -> None:
    assert connection.vendor == "postgresql"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname FROM pg_constraint "
            "WHERE connamespace = 'public'::regnamespace"
        )
        constraints = {row[0] for row in cursor.fetchall()}
        cursor.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
        indexes = {row[0] for row in cursor.fetchall()}

    assert REQUIRED_CONSTRAINTS <= constraints
    assert REQUIRED_INDEXES <= indexes


def test_foreign_key_delete_policies_match_the_storage_contract() -> None:
    expected = {
        "article_revision_article_fk": "ON DELETE CASCADE",
        "article_revision_section_fk": "ON DELETE SET NULL",
        "comment_author_fk": "ON DELETE SET NULL",
        "comment_thread_fk": "ON DELETE CASCADE",
        "comment_parent_fk": "ON DELETE CASCADE",
        "comment_root_fk": "ON DELETE CASCADE",
        "discovery_view_article_fk": "ON DELETE CASCADE",
        "discovery_bookmark_account_fk": "ON DELETE CASCADE",
        "discovery_reading_bookmark_account_fk": "ON DELETE CASCADE",
        "discovery_reading_bookmark_article_fk": "ON DELETE CASCADE",
        "discovery_article_like_account_fk": "ON DELETE CASCADE",
        "discovery_article_like_article_fk": "ON DELETE CASCADE",
        "comment_pin_thread_fk": "ON DELETE CASCADE",
        "comment_pin_comment_fk": "ON DELETE CASCADE",
        "comment_pin_pinned_by_fk": "ON DELETE SET NULL",
    }
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = ANY(%s)",
            (list(expected),),
        )
        definitions = dict(cursor.fetchall())

    assert set(definitions) == set(expected)
    for name, clause in expected.items():
        assert clause in definitions[name]


def test_migration_compatibility_contract_is_documented() -> None:
    record = Path(settings.BASE_DIR) / "docs/operations/migrations.md"
    assert record.is_file()
    text = record.read_text(encoding="utf-8")
    for required in (
        "expand/migrate/contract",
        "锁与兼容窗口",
        "备份与回滚限制",
        "空库读回",
    ):
        assert required in text
