from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.db import OperationalError
from django.template.loader import render_to_string

from apps.discovery.queries.profiles import (
    PublicProfileStats,
    profile_article_page,
    public_profile_stats,
)


def test_public_profile_stats_sum_the_existing_counter_queries(monkeypatch) -> None:
    monkeypatch.setattr(
        "apps.discovery.queries.profiles.public_article_ids_by_author",
        lambda **_: ("article-one", "article-two"),
    )
    monkeypatch.setattr(
        "apps.discovery.queries.profiles.article_view_counts",
        lambda **_: {"article-one": 7, "article-two": 5},
    )
    monkeypatch.setattr(
        "apps.discovery.queries.profiles.article_comment_counts",
        lambda **_: {"article-one": 2},
    )
    monkeypatch.setattr(
        "apps.discovery.queries.profiles.article_like_counts",
        lambda **_: {"article-two": 3},
    )

    stats = public_profile_stats(account_id=uuid4())

    assert stats == PublicProfileStats(2, 12, 2, 3)


def test_empty_public_profile_stats_do_not_query_counter_tables(monkeypatch) -> None:
    monkeypatch.setattr(
        "apps.discovery.queries.profiles.public_article_ids_by_author",
        lambda **_: (),
    )
    monkeypatch.setattr(
        "apps.discovery.queries.profiles.article_view_counts",
        lambda **_: pytest.fail("empty profiles must not query view counters"),
    )

    assert public_profile_stats(account_id=uuid4()) == PublicProfileStats(0, 0, 0, 0)


def test_public_profile_template_renders_identity_stats_and_k_mark() -> None:
    profile = SimpleNamespace(
        display_name="Profile-render",
        avatar_url=None,
        avatar_initial="P",
        profile_url="/people/00000000-0000-0000-0000-000000000001/",
    )
    stats = PublicProfileStats(1, 7, 2, 3)
    body = render_to_string(
        "discovery/public_profile.html",
        {
            "profile": profile,
            "profile_stats": stats,
            "filter_options": SimpleNamespace(sections=(), tags=()),
            "index_page": SimpleNamespace(
                items=(),
                total_items=0,
                page_number=1,
                total_pages=1,
                page_size=20,
            ),
            "pagination_form": SimpleNamespace(errors={}),
            "index_action": profile.profile_url,
            "clear_filter_url": profile.profile_url,
            "selected_section_id": None,
            "selected_tag_ids": (),
            "profile_filter_mode": True,
            "index_empty_title": "此处还没有公开文章",
            "index_empty_action_url": "/",
            "index_empty_action_label": "浏览最新文章",
        },
    )

    assert 'class="public-profile__stats-list"' in body
    assert "文章总数" in body
    assert "总浏览量" in body
    assert "总评论数" in body
    assert "总点赞数" in body
    assert "media/brand/k-mark" in body


def test_profile_fragment_skips_global_stats(monkeypatch) -> None:
    identity = SimpleNamespace(account_id=uuid4())
    monkeypatch.setattr(
        "apps.discovery.queries.profiles.resolve_profile_identity",
        lambda _: identity,
    )
    monkeypatch.setattr(
        "apps.discovery.queries.profiles.visible_articles_by_author",
        lambda **_: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "apps.discovery.queries.profiles.article_index_page",
        lambda _: "index",
    )
    monkeypatch.setattr(
        "apps.discovery.queries.profiles.public_profile_stats",
        lambda **_: pytest.fail("fragment requests must not load profile stats"),
    )

    page = profile_article_page(
        actor_id=None,
        account_id=identity.account_id,
        include_stats=False,
    )

    assert page is not None
    assert page.index_page == "index"
    assert page.stats is None


def test_profile_stats_fail_closed_when_counter_database_is_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "apps.discovery.queries.profiles.public_article_ids_by_author",
        lambda **_: (_ for _ in ()).throw(OperationalError("database unavailable")),
    )

    stats = public_profile_stats(account_id=uuid4())

    assert stats.available is False
    assert (
        stats.article_count,
        stats.view_count,
        stats.comment_count,
        stats.like_count,
    ) == (
        0,
        0,
        0,
        0,
    )
