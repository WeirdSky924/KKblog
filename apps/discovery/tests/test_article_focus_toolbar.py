from datetime import UTC, datetime
from uuid import uuid4

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Account, LoginSession, RoleAssignment
from apps.content.public import (
    ArticleSnapshot,
    ContentFormat,
    create_article,
    create_section,
    prepare_publication,
    publish_article,
)
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock
from apps.navigation.models import SiteConfiguration
from apps.navigation.public import update_article_explanation_settings

pytestmark = pytest.mark.django_db(transaction=True)


def _author_administrator() -> Account:
    account = Account.objects.create_account(
        email=f"article-focus-{uuid4()}@kaj.test",
        password="Valid-password-1",
        nickname="专注验收",
    )
    RoleAssignment.objects.bulk_create(
        (
            RoleAssignment(account=account, role=RoleAssignment.Role.AUTHOR),
            RoleAssignment(account=account, role=RoleAssignment.Role.ADMINISTRATOR),
        )
    )
    return account


def _published_article(author: Account) -> str:
    section = create_section(
        actor_id=author.id,
        name=f"专注工具验收-{uuid4()}",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    draft = create_article(
        actor_id=author.id,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.MARKDOWN,
            title="文章专注工具验收",
            body="# 正文\n\n用于验证登录用户阅读工具栏。",
            section_id=section.section_id,
        ),
        capacity_check=lambda: None,
    )
    clock = FrozenClock(datetime(2026, 10, 20, 8, 0, tzinfo=UTC))
    review = prepare_publication(
        actor_id=author.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        clock=clock,
    )
    publish_article(
        actor_id=author.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
        clock=clock,
    )
    return draft.article_id


def test_focus_tool_preserves_login_gate_and_renders_current_site_policy() -> None:
    author = _author_administrator()
    article_id = _published_article(author)
    config = SiteConfiguration.objects.get(pk=1)
    update_article_explanation_settings(
        actor_id=author.id,
        daily_limit=config.article_explanation_daily_limit,
        minute_limit=config.article_explanation_minute_limit,
        selection_limit=config.article_explanation_selection_limit,
        history_limit=config.article_explanation_history_limit,
        focus_idle_timeout_minutes=6,
        focus_manual_pause_limit=4,
        expected_version=config.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    url = reverse("article:detail", args=(article_id,))

    visitor_response = Client().get(url)
    assert visitor_response.status_code == 200
    assert b"data-article-focus-toggle" not in visitor_response.content

    authenticated = Client()
    token, _ = LoginSession.issue(
        account=author,
        remember=False,
        client_ip="127.0.0.1",
    )
    authenticated.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token
    member_response = authenticated.get(url)
    member_html = member_response.content.decode()

    assert member_response.status_code == 200
    assert "data-article-focus-toggle" in member_html
    assert 'data-focus-idle-timeout-minutes="6"' in member_html
    assert 'data-focus-manual-pause-limit="4"' in member_html
    assert "data-article-focus-pause" in member_html
    assert 'class="article-focus-timer"' in member_html
