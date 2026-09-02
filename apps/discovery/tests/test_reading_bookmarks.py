from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.db import ProgrammingError
from django.test import Client
from django.urls import reverse

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
from apps.discovery.services import (
    ReadingBookmarkUnavailableError,
    reading_bookmark_progress,
    save_reading_bookmark,
)
from apps.discovery.services import reading_bookmarks as reading_bookmark_owner

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str, *, roles: tuple[str, ...] = ()):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    for role in roles:
        role_model.objects.create(account=account, role=role)
    return account


def _published_article(author, *, label: str) -> str:
    section = create_section(
        actor_id=author.id,
        name=f"阅读书签-{label}-{uuid4()}",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    draft = create_article(
        actor_id=author.id,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.MARKDOWN,
            title=f"阅读书签测试文章-{label}",
            body="# 开始\n\n正文第一段。\n\n## 中段\n\n正文第二段。",
            section_id=section.section_id,
        ),
        capacity_check=lambda: None,
    )
    clock = FrozenClock(datetime(2026, 8, 6, 12, 0, tzinfo=UTC))
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


def _logged_in_client(account) -> Client:
    session_model = apps.get_model("accounts", "LoginSession")
    raw_token, _ = session_model.issue(account=account, remember=False)
    client = Client(REMOTE_ADDR="127.0.0.1")
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = raw_token
    return client


def test_reading_bookmark_updates_one_row_per_account_and_article() -> None:
    author = _account("reading-bookmark-author", roles=("AUTHOR", "ADMINISTRATOR"))
    member = _account("reading-bookmark-member")
    other_member = _account("reading-bookmark-other-member")
    first_article = _published_article(author, label="first")
    second_article = _published_article(author, label="second")

    first = save_reading_bookmark(
        account_id=member.id,
        article_id=first_article,
        progress=Decimal("0.250000"),
    )
    updated = save_reading_bookmark(
        account_id=member.id,
        article_id=first_article,
        progress=Decimal("0.750000"),
    )
    save_reading_bookmark(
        account_id=member.id,
        article_id=second_article,
        progress=Decimal("0.500000"),
    )
    save_reading_bookmark(
        account_id=other_member.id,
        article_id=first_article,
        progress=Decimal("0.125000"),
    )

    model = apps.get_model("discovery", "ReadingBookmark")
    assert first.created is True
    assert updated.created is False
    assert (
        model.objects.filter(account_id=member.id, article_id=first_article).count()
        == 1
    )
    assert reading_bookmark_progress(
        account_id=member.id, article_id=first_article
    ) == Decimal("0.750000")
    assert reading_bookmark_progress(
        account_id=member.id, article_id=second_article
    ) == Decimal("0.500000")
    assert reading_bookmark_progress(
        account_id=other_member.id, article_id=first_article
    ) == Decimal("0.125000")


def test_saving_reading_bookmark_does_not_render_article(monkeypatch) -> None:
    author = _account(
        "reading-bookmark-lightweight-author",
        roles=("AUTHOR", "ADMINISTRATOR"),
    )
    member = _account("reading-bookmark-lightweight-member")
    article_id = _published_article(author, label="lightweight")

    def fail_render(*args, **kwargs):
        del args, kwargs
        raise AssertionError("saving a reading bookmark must not render the article")

    monkeypatch.setattr("apps.content.queries.access._reader_media", fail_render)

    state = save_reading_bookmark(
        account_id=member.id,
        article_id=article_id,
        progress=Decimal("0.375000"),
    )

    assert state.article_id == article_id
    assert state.revision_id


def test_reading_bookmark_http_requires_login_validates_and_reads_back(
    monkeypatch,
) -> None:
    author = _account("reading-bookmark-http-author", roles=("AUTHOR", "ADMINISTRATOR"))
    member = _account("reading-bookmark-http-member")
    article_id = _published_article(author, label="http")
    detail_url = reverse("article:detail", kwargs={"article_id": article_id})
    save_url = reverse("article:reading-bookmark", kwargs={"article_id": article_id})

    anonymous = Client(REMOTE_ADDR="127.0.0.1")
    anonymous_page = anonymous.get(detail_url)
    anonymous_html = anonymous_page.content.decode()
    assert anonymous_page.status_code == 200
    assert 'id="article-mobile-action-menu"' in anonymous_html
    assert "data-article-mobile-menu" in anonymous_html
    assert "data-article-mobile-menu-toggle" in anonymous_html
    assert 'aria-controls="article-mobile-action-menu"' in anonymous_html
    assert 'aria-expanded="false"' in anonymous_html
    assert 'data-article-action="bookmark"' in anonymous_html
    assert 'data-article-action="copy"' in anonymous_html
    assert 'data-article-action="reading-bookmark"' in anonymous_html
    assert 'data-article-action="like"' in anonymous_html
    assert "data-article-scroll-top" in anonymous_html
    assert "data-reading-bookmark-save" in anonymous_html
    assert "data-reading-bookmark-goto-login" in anonymous_html
    assert "登录后保存阅读书签" in anonymous_html

    denied = anonymous.post(save_url, {"progress": "0.375000"})
    assert denied.status_code == 302
    assert denied.url.startswith(reverse("accounts:login"))

    client = _logged_in_client(member)
    invalid = client.post(save_url, {"progress": "1.100000"})
    assert invalid.status_code == 422
    assert invalid.json() == {
        "ok": False,
        "error": "阅读位置无效。",
    }

    saved = client.post(save_url, {"progress": "0.625000"})
    assert saved.status_code == 200
    assert saved.json() == {
        "ok": True,
        "progress": "0.625000",
        "created": True,
    }

    page = client.get(detail_url)
    assert page.status_code == 200
    assert page.context["reading_bookmark_progress"] == Decimal("0.625000")
    html = page.content.decode()
    assert "前往书签" in html
    assert f'action="{save_url}"' in html
    assert 'id="article-mobile-action-menu"' in html
    assert "data-article-mobile-menu-toggle" in html
    assert "data-reading-bookmark-save" in html
    assert "data-reading-bookmark-goto" in html

    def unavailable_save(**kwargs):
        del kwargs
        raise ReadingBookmarkUnavailableError

    monkeypatch.setattr(
        "apps.discovery.views.save_reading_bookmark",
        unavailable_save,
    )
    unavailable = client.post(save_url, {"progress": "0.500000"})
    assert unavailable.status_code == 503
    assert unavailable.json() == {
        "ok": False,
        "error": "阅读书签正在升级，请稍后再试。",
    }


def test_article_without_reading_bookmark_disables_goto_control() -> None:
    author = _account(
        "reading-bookmark-empty-author", roles=("AUTHOR", "ADMINISTRATOR")
    )
    member = _account("reading-bookmark-empty-member")
    article_id = _published_article(author, label="empty")

    page = _logged_in_client(member).get(
        reverse("article:detail", kwargs={"article_id": article_id})
    )

    assert page.status_code == 200
    assert page.context["reading_bookmark_progress"] is None
    assert "data-reading-bookmark-goto disabled" in page.content.decode()


def test_missing_reading_bookmark_table_keeps_article_read_available(
    monkeypatch,
) -> None:
    error = ProgrammingError("missing reading bookmark table")
    cause = RuntimeError("undefined table")
    cause.sqlstate = "42P01"
    error.__cause__ = cause

    def missing_table(*args, **kwargs):
        del args, kwargs
        raise error

    monkeypatch.setattr(
        reading_bookmark_owner.ReadingBookmark.objects,
        "filter",
        missing_table,
    )

    assert (
        reading_bookmark_progress(
            account_id=uuid4(),
            article_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        )
        is None
    )
