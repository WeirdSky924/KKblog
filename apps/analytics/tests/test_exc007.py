from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from django.apps import apps
from django.conf import settings
from django.test import override_settings
from django.urls import reverse

from apps.analytics.services.retention import (
    UmamiRetentionCounts,
    expire_umami_data,
    shanghai_retention_date,
)
from apps.core.events.outbox import envelope_from_model
from apps.core.time.clock import FrozenClock
from apps.operations.public import (
    RetryableTaskError,
    TaskFinalFailed,
    TaskRetryScheduled,
    execute_tracked_task,
    is_operational_task,
    send_pending_operational_alert_emails,
)
from config.environment import ConfigurationError, load_production_environment
from config.operational_email import send_configured_operational_email
from config.outbox_transport import build_application_event_transport
from tests.fixtures.accounts import bootstrap_test_administrator

pytestmark = pytest.mark.django_db(transaction=True)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WEBSITE_ID = "8b52c6fc-8d26-48b4-8ec8-5f2a67587044"
NOW = datetime(2026, 7, 27, 20, 15, tzinfo=UTC)


class _ComposeLoader(yaml.SafeLoader):
    pass


_ComposeLoader.add_constructor(
    "!override",
    lambda loader, node: loader.construct_sequence(node),
)


def _authenticate(client, account) -> None:
    session_model = apps.get_model("accounts", "LoginSession")
    token, _ = session_model.issue(account=account, remember=False)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token


@override_settings(ANALYTICS_ENABLED=True, ANALYTICS_WEBSITE_ID=WEBSITE_ID)
def test_tracker_is_in_shared_shell_and_admin_entry_is_guarded(client) -> None:
    public = client.get(reverse("public:home"))
    body = public.content.decode()
    assert public.status_code == 200
    assert 'src="/analytics/script.js"' in body
    assert 'data-host-url="/"' in body
    assert f'data-website-id="{WEBSITE_ID}"' in body

    denied = client.get(reverse("admin:analytics"))
    assert denied.status_code == 403

    account_model = apps.get_model("accounts", "Account")
    account = account_model.objects.create_account(
        email=f"analytics-user-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    _authenticate(client, account)
    assert client.get(reverse("admin:analytics")).status_code == 403

    client.cookies.clear()
    admin = bootstrap_test_administrator()
    _authenticate(client, admin)
    allowed = client.get(reverse("admin:analytics"))
    allowed_body = allowed.content.decode()
    assert allowed.status_code == 200
    assert 'src="/admin/analytics/umami/"' in allowed_body
    assert "Umami" in allowed_body


@override_settings(ANALYTICS_ENABLED=True, ANALYTICS_WEBSITE_ID=WEBSITE_ID)
def test_internal_proxy_authorization_requires_marker_admin_and_owned_path(
    client,
) -> None:
    endpoint = reverse("analytics:internal-authorize")
    assert client.get(endpoint).status_code == 404
    assert (
        client.get(
            endpoint,
            HTTP_X_KAJ_INTERNAL_AUTH="1",
            HTTP_X_FORWARDED_URI="/api/websites",
        ).status_code
        == 404
    )

    admin = bootstrap_test_administrator()
    _authenticate(client, admin)
    public_collect = client.get(
        endpoint,
        HTTP_X_KAJ_INTERNAL_AUTH="1",
        HTTP_X_FORWARDED_URI="/analytics/collect",
    )
    assert public_collect.status_code == 404
    authorized = client.get(
        endpoint,
        HTTP_X_KAJ_INTERNAL_AUTH="1",
        HTTP_X_FORWARDED_URI="/api/websites",
    )
    assert authorized.status_code == 204
    assert authorized.headers["Cache-Control"] == "private, no-store"


@override_settings(ANALYTICS_ENABLED=False, ANALYTICS_WEBSITE_ID="")
def test_disabled_analytics_fails_closed_without_browser_configuration(client) -> None:
    body = client.get(reverse("public:home")).content.decode()
    assert "/analytics/script.js" not in body
    assert WEBSITE_ID not in body

    admin = bootstrap_test_administrator()
    _authenticate(client, admin)
    response = client.get(reverse("admin:analytics"))
    assert response.status_code == 503
    assert "/admin/analytics/umami/" not in response.content.decode()


def test_test_environment_disables_analytics_by_default() -> None:
    assert settings.ANALYTICS_ENABLED is False
    assert settings.ANALYTICS_DATABASE_URL == ""
    assert settings.ANALYTICS_WEBSITE_ID == ""


@dataclass
class _MemoryRetentionStore:
    moments: list[datetime]

    def delete_before(self, cutoff: datetime) -> UmamiRetentionCounts:
        removed = [moment for moment in self.moments if moment < cutoff]
        self.moments = [moment for moment in self.moments if moment >= cutoff]
        return UmamiRetentionCounts(website_events=len(removed))


def test_retention_uses_strict_30_day_boundary_and_is_repeatable() -> None:
    cutoff = NOW - timedelta(days=30)
    store = _MemoryRetentionStore(
        [
            cutoff - timedelta(microseconds=1),
            cutoff,
            cutoff + timedelta(microseconds=1),
        ]
    )
    first = expire_umami_data(store=store, clock=FrozenClock(NOW))
    second = expire_umami_data(store=store, clock=FrozenClock(NOW))

    assert first.cutoff == cutoff
    assert first.counts.website_events == 1
    assert second.counts.total == 0
    assert store.moments == [cutoff, cutoff + timedelta(microseconds=1)]
    assert shanghai_retention_date(clock=FrozenClock(NOW)).isoformat() == "2026-07-28"


def test_daily_task_is_tracked_idempotently_and_is_operational() -> None:
    calls = []

    def service(value: str) -> str:
        calls.append(value)
        return "umami-retention:1"

    first = execute_tracked_task(
        task_name="apps.analytics.expire_umami_data",
        business_object="umami-retention:2026-07-28",
        idempotency_key="umami-retention:2026-07-28",
        celery_id="00000000-0000-0000-0000-000000000071",
        service=service,
        clock=FrozenClock(NOW),
    )
    repeated = execute_tracked_task(
        task_name="apps.analytics.expire_umami_data",
        business_object="umami-retention:2026-07-28",
        idempotency_key="umami-retention:2026-07-28",
        celery_id="00000000-0000-0000-0000-000000000072",
        service=service,
        clock=FrozenClock(NOW),
    )

    assert first.result_ref == repeated.result_ref == "umami-retention:1"
    assert calls == ["umami-retention:2026-07-28"]
    task_run_model = apps.get_model("operations", "TaskRun")
    run = task_run_model.objects.get(task_name="apps.analytics.expire_umami_data")
    assert run.status == "succeeded"
    assert run.attempt == 1
    assert is_operational_task("apps.analytics.expire_umami_data") is True
    schedule = settings.CELERY_BEAT_SCHEDULE["analytics-expire-umami-data"]
    assert schedule["task"] == "apps.analytics.expire_umami_data"


def test_third_retention_failure_notifies_admin_and_opens_email_window(
    mailpit,
) -> None:
    admin = bootstrap_test_administrator()

    def fail_retention(_business_object: str) -> str:
        raise RetryableTaskError("analytics.retention_database_unavailable.v1")

    moments = (
        NOW,
        NOW + timedelta(seconds=60),
        NOW + timedelta(seconds=360),
    )
    for index, moment in enumerate(moments, start=1):
        expected = TaskFinalFailed if index == 3 else TaskRetryScheduled
        with pytest.raises(expected):
            execute_tracked_task(
                task_name="apps.analytics.expire_umami_data",
                business_object="umami-retention:2026-07-28",
                idempotency_key="umami-retention:2026-07-28",
                celery_id=f"00000000-0000-0000-0000-00000000008{index}",
                service=fail_retention,
                jitter=lambda _base: 0,
                clock=FrozenClock(moment),
            )

    task_run_model = apps.get_model("operations", "TaskRun")
    run = task_run_model.objects.get(task_name="apps.analytics.expire_umami_data")
    assert run.status == "final_failed"
    assert run.attempt == 3
    outbox_model = apps.get_model("core", "OutboxEvent")
    event = outbox_model.objects.get(event_type="task.final_failed.v1")
    transport = build_application_event_transport()
    transport.publish(envelope_from_model(event))
    transport.publish(envelope_from_model(event))

    alert_model = apps.get_model("operations", "OperationalAlert")
    window_model = apps.get_model("operations", "OperationalAlertEmailWindow")
    notification_model = apps.get_model("notifications", "Notification")
    receipt_model = apps.get_model("notifications", "NotificationReceipt")
    assert alert_model.objects.count() == 1
    assert window_model.objects.count() == 1
    assert (
        notification_model.objects.filter(template_key="task.final_failed.v1").count()
        == 1
    )
    assert receipt_model.objects.filter(recipient=admin).count() == 1

    sent = send_pending_operational_alert_emails(
        sender=send_configured_operational_email,
        clock=FrozenClock(moments[-1]),
    )
    assert sent.sent == 1
    messages = mailpit.messages()
    assert len(messages) == 1
    assert messages[0]["To"][0]["Address"] == "admin@kaj.test"


def _production_values() -> dict[str, str]:
    return {
        "DJANGO_SECRET_KEY": "x" * 64,
        "KAJ_PUBLIC_URL": "https://blog.kaj.example.org",
        "KAJ_ADMIN_EMAIL": "admin@kaj.example.org",
        "DEFAULT_FROM_EMAIL": "no-reply@kaj.example.org",
        "EMAIL_HOST": "smtp.kaj.example.org",
        "EMAIL_PORT": "465",
        "EMAIL_HOST_USER": "no-reply@kaj.example.org",
        "EMAIL_HOST_PASSWORD": "smtp-test-credential",
        "EMAIL_USE_TLS": "false",
        "EMAIL_USE_SSL": "true",
        "DATABASE_URL": "postgresql://kaj:strong@db:5432/kaj",
        "REDIS_URL": "rediss://redis:6379/0",
        "KAJ_MEDIA_ROOT": "/srv/kaj/media",
        "KAJ_INITIAL_ADMIN_PASSWORD": "Strong-Initial-Credential-711!",
        "KAJ_TRUSTED_PROXY_CIDRS": "172.16.0.0/12",
        "KAJ_UMAMI_DATABASE_URL": "postgresql://umami:strong@db:5432/umami",
        "KAJ_UMAMI_APP_SECRET": "u" * 48,
        "KAJ_UMAMI_WEBSITE_ID": WEBSITE_ID,
    }


def test_production_requires_valid_umami_configuration_without_leaking_values() -> None:
    loaded = load_production_environment(_production_values())
    assert loaded.umami_website_id == WEBSITE_ID
    assert loaded.umami_database_url.endswith("/umami")
    assert not hasattr(loaded, "umami_app_secret")
    assert "strong" not in repr(loaded)

    for key in (
        "KAJ_UMAMI_DATABASE_URL",
        "KAJ_UMAMI_WEBSITE_ID",
    ):
        values = _production_values()
        secret = values.pop(key)
        with pytest.raises(ConfigurationError, match=key) as captured:
            load_production_environment(values)
        assert secret not in str(captured.value)

    values = _production_values()
    values.pop("KAJ_UMAMI_APP_SECRET")
    load_production_environment(values)

    values = _production_values()
    values["KAJ_UMAMI_DATABASE_URL"] = "postgresql://umami:private@db:5432/kaj"
    with pytest.raises(ConfigurationError, match="KAJ_UMAMI_DATABASE_URL") as captured:
        load_production_environment(values)
    assert "private" not in str(captured.value)


def test_compose_and_caddy_keep_umami_private_with_exact_public_collection_paths() -> (
    None
):
    compose = yaml.safe_load(
        (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    )
    umami = compose["services"]["umami"]
    assert umami["image"].endswith("umami:postgresql-v2.19.0}")
    assert "ports" not in umami
    assert umami["networks"] == ["backend", "analytics"]
    assert umami["environment"]["COLLECT_API_ENDPOINT"] == "/analytics/collect"
    assert umami["environment"]["TRACKER_SCRIPT_NAME"] == "analytics/script.js"
    assert compose["services"]["caddy"]["networks"] == ["frontend", "analytics"]

    proxy = (PROJECT_ROOT / "docker/caddy/analytics-proxy.caddy").read_text(
        encoding="utf-8"
    )
    assert "path /analytics/script.js" in proxy
    assert "path /analytics/collect" in proxy
    assert "method GET HEAD" in proxy
    assert "method POST OPTIONS" in proxy
    assert "forward_auth" in proxy
    assert 'header_up X-Kaj-Internal-Auth "1"' in proxy
    assert "header_up -Authorization" in proxy
    assert proxy.count("header_up -Cookie") == 3
    assert "kaj_session=[^;]*" not in proxy
    assert proxy.index("@analytics_collection") < proxy.index("@analytics_dashboard")
    assert "reverse_proxy {$KAJ_UMAMI_UPSTREAM:umami:3000}" in proxy

    production = yaml.load(
        (PROJECT_ROOT / "docker/caddy/compose.production.yaml").read_text(
            encoding="utf-8"
        ),
        Loader=_ComposeLoader,
    )
    app_environment = production["x-production-environment"]
    assert "KAJ_UMAMI_APP_SECRET" not in app_environment
    assert "KAJ_UMAMI_WEBSITE_ID" in app_environment
    assert production["services"]["umami"]["environment"]["APP_SECRET"]
    umami_command = "\n".join(production["services"]["umami"]["command"])
    assert "APP_SECRET" in umami_command
    assert "wc -c" in umami_command
