from uuid import uuid4

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Account, LoginSession, RoleAssignment
from apps.administration.forms.site_settings import ArticleExplanationSettingsForm
from apps.navigation.models import SiteConfiguration
from apps.navigation.public import (
    SiteContentCommandError,
    article_explanation_settings,
    update_article_explanation_settings,
)
from apps.operations.models import AuditEntry


def _account(*, administrator: bool) -> Account:
    account = Account.objects.create_account(
        email=f"focus-settings-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    if administrator:
        RoleAssignment.objects.create(
            account=account,
            role=RoleAssignment.Role.ADMINISTRATOR,
        )
    return account


def _login(client: Client, account: Account) -> None:
    token, _ = LoginSession.issue(
        account=account,
        remember=False,
        client_ip="127.0.0.1",
    )
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token


def _update(actor_id, *, expected_version: int, idle_minutes: int, pause_limit: int):
    current = SiteConfiguration.objects.get(pk=1)
    return update_article_explanation_settings(
        actor_id=actor_id,
        daily_limit=current.article_explanation_daily_limit,
        minute_limit=current.article_explanation_minute_limit,
        selection_limit=current.article_explanation_selection_limit,
        history_limit=current.article_explanation_history_limit,
        focus_idle_timeout_minutes=idle_minutes,
        focus_manual_pause_limit=pause_limit,
        expected_version=expected_version,
        trace_code=f"trc_{'f' * 26}",
        client_ip="127.0.0.1",
    )


def test_focus_fields_have_default_and_admin_range_contract() -> None:
    form = ArticleExplanationSettingsForm()
    idle = form.fields["focus_idle_timeout_minutes"]
    pauses = form.fields["focus_manual_pause_limit"]

    assert (idle.initial, idle.min_value, idle.max_value) == (3, 1, 15)
    assert (pauses.initial, pauses.min_value, pauses.max_value) == (3, 1, 10)


@pytest.mark.django_db(transaction=True)
def test_focus_policy_defaults_are_read_from_site_configuration() -> None:
    settings_item = article_explanation_settings()
    assert settings_item.focus_idle_timeout_minutes == 3
    assert settings_item.focus_manual_pause_limit == 3


@pytest.mark.django_db(transaction=True)
def test_admin_can_update_focus_policy_with_audit_and_version_readback() -> None:
    administrator = _account(administrator=True)
    row = SiteConfiguration.objects.get(pk=1)

    result = _update(
        administrator.id,
        expected_version=row.row_version,
        idle_minutes=7,
        pause_limit=4,
    )

    row.refresh_from_db()
    settings_item = article_explanation_settings()
    audit = AuditEntry.objects.get(
        action="navigation.article_explanation_settings.update",
        target_id="site",
    )
    assert result.changed is True
    assert row.row_version == 2
    assert (
        settings_item.focus_idle_timeout_minutes,
        settings_item.focus_manual_pause_limit,
    ) == (7, 4)
    assert audit.before_safe["focus_idle_timeout_minutes"] == 3
    assert audit.after_safe["focus_idle_timeout_minutes"] == 7
    assert audit.after_safe["focus_manual_pause_limit"] == 4


@pytest.mark.parametrize(
    ("idle_minutes", "pause_limit"),
    ((0, 3), (16, 3), (3, 0), (3, 11)),
)
@pytest.mark.django_db(transaction=True)
def test_focus_policy_rejects_out_of_range_values_without_writing(
    idle_minutes: int,
    pause_limit: int,
) -> None:
    administrator = _account(administrator=True)
    row = SiteConfiguration.objects.get(pk=1)

    with pytest.raises(SiteContentCommandError) as error:
        _update(
            administrator.id,
            expected_version=row.row_version,
            idle_minutes=idle_minutes,
            pause_limit=pause_limit,
        )

    row.refresh_from_db()
    assert error.value.code == "navigation.article_explanation_settings_invalid.v1"
    assert row.row_version == 1
    assert row.focus_idle_timeout_minutes == 3
    assert row.focus_manual_pause_limit == 3


@pytest.mark.django_db(transaction=True)
def test_focus_policy_rejects_non_admin_and_stale_versions() -> None:
    administrator = _account(administrator=True)
    ordinary = _account(administrator=False)
    row = SiteConfiguration.objects.get(pk=1)

    with pytest.raises(SiteContentCommandError) as forbidden:
        _update(
            ordinary.id,
            expected_version=row.row_version,
            idle_minutes=4,
            pause_limit=3,
        )
    assert forbidden.value.code == "navigation.site_admin_required.v1"

    _update(
        administrator.id,
        expected_version=row.row_version,
        idle_minutes=4,
        pause_limit=3,
    )
    with pytest.raises(SiteContentCommandError) as conflict:
        _update(
            administrator.id,
            expected_version=row.row_version,
            idle_minutes=5,
            pause_limit=3,
        )
    assert conflict.value.code == "navigation.site_edit_conflict.v1"


@pytest.mark.django_db(transaction=True)
def test_admin_reading_settings_page_exposes_and_saves_focus_policy(
    client: Client,
) -> None:
    administrator = _account(administrator=True)
    _login(client, administrator)
    url = reverse("admin:article-explanation-settings")

    page = client.get(url)
    assert page.status_code == 200
    assert "文章阅读设置" in page.content.decode()
    assert 'name="focus_idle_timeout_minutes"' in page.content.decode()
    assert 'name="focus_manual_pause_limit"' in page.content.decode()

    row = SiteConfiguration.objects.get(pk=1)
    response = client.post(
        url,
        {
            "daily_limit": str(row.article_explanation_daily_limit),
            "minute_limit": str(row.article_explanation_minute_limit),
            "selection_limit": str(row.article_explanation_selection_limit),
            "history_limit": str(row.article_explanation_history_limit),
            "focus_idle_timeout_minutes": "6",
            "focus_manual_pause_limit": "5",
            "expected_version": str(row.row_version),
        },
    )

    assert response.status_code == 302
    row.refresh_from_db()
    assert (row.focus_idle_timeout_minutes, row.focus_manual_pause_limit) == (6, 5)


@pytest.mark.django_db(transaction=True)
def test_reading_settings_page_rejects_non_admin(client: Client) -> None:
    ordinary = _account(administrator=False)
    _login(client, ordinary)

    assert client.get(reverse("admin:article-explanation-settings")).status_code == 403
