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
    "article_revision_tiptap_schema_shape",
    "article_revision_based_on_same_article_fk",
    "article_revision_restore_source_same_article_fk",
    "content_publication_article_revision_unique",
    "content_publication_revision_same_article_fk",
    "content_revision_tag_unique",
    "content_article_tag_unique",
    "media_asset_size_range",
    "media_asset_hero_format",
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
    "opp_source_type_valid",
    "opp_source_official_url_unique",
    "opp_source_public_requires_enabled",
    "opp_source_request_interval_min",
    "opp_filter_kind_name_unique",
    "opp_source_filter_unique",
    "opp_source_identity_unique",
    "opp_filter_assignment_unique",
    "opp_check_target_shape",
    "opp_check_completion_shape",
    "opp_bookmark_account_job_unique",
    "opp_settings_singleton",
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
    "content_pub_article_time_idx",
    "content_tag_name_unique",
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
    "opp_source_public_idx",
    "opp_public_list_idx",
    "opp_admin_source_idx",
    "opp_filter_assignment_idx",
    "opp_bookmark_account_idx",
    "opp_check_source_history_idx",
    "opp_review_open_kind_unique",
    "opp_review_queue_idx",
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


def test_publication_history_migration_backfills_events_and_current_pointer() -> None:
    source_url = os.environ["KAJ_TEST_DATABASE_URL"]
    database_name = f"kaj_test_t14_history_{uuid4().hex[:10]}"
    target_url = _database_url(source_url, database_name)
    with _admin_connection(source_url) as admin:
        admin.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
        )
    environment = os.environ.copy()
    environment.update(
        DJANGO_SETTINGS_MODULE="config.settings.test",
        KAJ_TEST_DATABASE_URL=target_url,
    )
    seed = """
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from django.apps import apps
from apps.content.public import ArticleSnapshot, ContentFormat, create_article, create_section, prepare_publication, publish_article, save_revision
from apps.core.events.models import OutboxEvent
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock

Account = apps.get_model("accounts", "Account")
RoleAssignment = apps.get_model("accounts", "RoleAssignment")
admin = Account.objects.create_account(email=f"history-admin-{uuid4()}@kaj.test", password="Valid-password-1")
author = Account.objects.create_account(email=f"history-author-{uuid4()}@kaj.test", password="Valid-password-1")
RoleAssignment.objects.create(account=admin, role="AUTHOR")
RoleAssignment.objects.create(account=admin, role="ADMINISTRATOR")
RoleAssignment.objects.create(account=author, role="AUTHOR")
section = create_section(actor_id=admin.id, name=f"迁移分区-{uuid4()}", trace_code=new_trace_code(), client_ip="127.0.0.1")
snapshot = ArticleSnapshot(content_format=ContentFormat.MARKDOWN, title="迁移第一版", body="第一版正文", section_id=section.section_id)
first = create_article(actor_id=author.id, snapshot=snapshot, capacity_check=lambda: None)
first_clock = FrozenClock(datetime(2026, 8, 9, 3, 0, tzinfo=UTC))
article = apps.get_model("content", "Article").objects.get(pk=first.article_id)
review = prepare_publication(actor_id=author.id, article_id=first.article_id, revision_id=first.revision_id, expected_row_version=article.row_version, clock=first_clock)
publish_article(actor_id=author.id, article_id=first.article_id, revision_id=first.revision_id, expected_row_version=article.row_version, review_token=review.token, trace_code=new_trace_code(), clock=first_clock)
article.refresh_from_db()
latest = save_revision(actor_id=author.id, article_id=first.article_id, expected_row_version=article.row_version, snapshot=ArticleSnapshot(content_format=ContentFormat.MARKDOWN, title="迁移第二版", body="第二版正文", section_id=section.section_id), capacity_check=lambda: None)
second_clock = FrozenClock(first_clock.now() + timedelta(days=1))
article.refresh_from_db()
review = prepare_publication(actor_id=author.id, article_id=first.article_id, revision_id=latest.revision_id, expected_row_version=article.row_version, clock=second_clock)
publish_article(actor_id=author.id, article_id=first.article_id, revision_id=latest.revision_id, expected_row_version=article.row_version, review_token=review.token, trace_code=new_trace_code(), clock=second_clock)
OutboxEvent.objects.filter(event_type="article.published.v1", aggregate_id=first.article_id, payload__revision_id=latest.revision_id).delete()
    """
    try:
        prepared = subprocess.run(
            [sys.executable, "manage.py", "migrate", "--noinput"],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert prepared.returncode == 0, prepared.stderr
        before = subprocess.run(
            [sys.executable, "manage.py", "migrate", "content", "0015", "--noinput"],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert before.returncode == 0, before.stderr
        seeded = subprocess.run(
            [sys.executable, "manage.py", "shell", "-c", seed],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert seeded.returncode == 0, seeded.stderr
        with psycopg.connect(target_url) as database:
            revisions = database.execute(
                "SELECT id, created_at FROM article_revision ORDER BY sequence"
            ).fetchall()
            event_time = database.execute(
                "SELECT occurred_at FROM core_outbox_event "
                "WHERE event_type = 'article.published.v1'"
            ).fetchone()[0]
            current_time = database.execute(
                "SELECT last_published_at FROM article"
            ).fetchone()[0]
        migrated = subprocess.run(
            [sys.executable, "manage.py", "migrate", "content", "0016", "--noinput"],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert migrated.returncode == 0, migrated.stderr
        with psycopg.connect(target_url) as database:
            publications = database.execute(
                "SELECT revision_id, published_at "
                "FROM content_article_publication ORDER BY published_at"
            ).fetchall()
        assert publications == [
            (revisions[0][0], event_time),
            (revisions[1][0], current_time),
        ]
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


def test_friend_link_logo_migration_releases_bindings_without_deleting_files(
    tmp_path: Path,
) -> None:
    source_url = os.environ["KAJ_TEST_DATABASE_URL"]
    database_name = f"kaj_test_t15_friend_{uuid4().hex[:10]}"
    target_url = _database_url(source_url, database_name)
    with _admin_connection(source_url) as admin:
        admin.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
        )
    environment = os.environ.copy()
    environment.update(
        DJANGO_SETTINGS_MODULE="config.settings.test",
        KAJ_TEST_DATABASE_URL=target_url,
    )
    try:
        prepared = subprocess.run(
            [sys.executable, "manage.py", "migrate", "--noinput"],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert prepared.returncode == 0, prepared.stderr
        before = subprocess.run(
            [sys.executable, "manage.py", "migrate", "navigation", "0006", "--noinput"],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert before.returncode == 0, before.stderr
        legacy_file = tmp_path / "friend-logo.png"
        legacy_file.write_bytes(b"legacy-logo-bytes")
        link_id = uuid4()
        asset_id = "01KZSXM5QKQ1KJ10KMJXKE1500"
        binding_id = "01KZSXM5QKQ1KJ10KMJXKE1501"
        with psycopg.connect(target_url) as database:
            nickname = f"friend-{uuid4().hex[:8]}"
            account_id = database.execute(
                "INSERT INTO account (id, email, password_hash, nickname, normalized_nickname, status, theme, "
                "must_change_password, auto_republish_enabled, attachment_upload_enabled, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, 'ACTIVE', 'LIGHT', false, false, false, now(), now()) RETURNING id",
                (
                    uuid4(),
                    f"friend-migration-{uuid4()}@kaj.test",
                    "test-only-hash",
                    nickname,
                    nickname,
                ),
            ).fetchone()[0]
            database.execute(
                "INSERT INTO friend_link (id, name, url, description, logo_asset_id, position, row_version, created_at, updated_at) "
                "VALUES (%s, '旧友链', 'https://example.com', '旧 Logo 迁移', %s, 0, 1, now(), now())",
                (link_id, asset_id),
            )
            database.execute(
                "INSERT INTO media_asset (id, owner_id, purpose, storage_key, original_name, detected_mime, size_bytes, sha256, width, height, state, created_at, deleted_at) "
                "VALUES (%s, %s, 'FRIEND_LOGO', 'site/friend-links/legacy.png', 'legacy.png', 'image/png', 17, %s, 1, 1, 'ACTIVE', now(), NULL)",
                (asset_id, account_id, "a" * 64),
            )
            database.execute(
                "INSERT INTO media_binding (id, asset_id, target_type, target_id, slot, created_at) "
                "VALUES (%s, %s, 'friend_link', %s, 'logo', now())",
                (binding_id, asset_id, str(link_id)),
            )
            database.commit()

        migrated = subprocess.run(
            [sys.executable, "manage.py", "migrate", "navigation", "0007", "--noinput"],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert migrated.returncode == 0, migrated.stderr
        with psycopg.connect(target_url) as database:
            assert database.execute(
                "SELECT logo_asset_id FROM friend_link WHERE id = %s", (link_id,)
            ).fetchone() == ("",)
            assert database.execute(
                "SELECT count(*) FROM media_binding WHERE target_type = 'friend_link'"
            ).fetchone() == (0,)
            assert database.execute(
                "SELECT state FROM media_asset WHERE id = %s", (asset_id,)
            ).fetchone() == ("DELETE_PENDING",)
        assert legacy_file.read_bytes() == b"legacy-logo-bytes"
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


def test_site_configuration_has_nullable_hero_media_reference() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT is_nullable, character_maximum_length "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' "
            "AND table_name = 'site_configuration' "
            "AND column_name = 'hero_asset_id'"
        )
        column = cursor.fetchone()

    assert column == ("YES", 26)


def test_foreign_key_delete_policies_match_the_storage_contract() -> None:
    expected = {
        "article_revision_article_fk": "ON DELETE CASCADE",
        "article_revision_section_fk": "ON DELETE SET NULL",
        "content_publication_revision_same_article_fk": "ON DELETE CASCADE",
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
