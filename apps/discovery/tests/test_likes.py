from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
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
from apps.discovery.profile_identity import (
    configure_profile_identity_collection_provider,
)
from apps.discovery.queries import home_article_page
from apps.discovery.queries.like_counts import article_like_counts
from apps.discovery.services import is_article_liked, set_article_like

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
        name=f"点赞分区-{label}-{uuid4()}",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    draft = create_article(
        actor_id=author.id,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.MARKDOWN,
            title=f"点赞测试文章-{label}",
            body="正文",
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


def _profile_identities(account_ids):
    account_model = apps.get_model("accounts", "Account")
    return tuple(
        SimpleNamespace(
            account_id=account.id,
            display_name=account.nickname or account.email.partition("@")[0],
            avatar_url=None,
            avatar_initial=(account.nickname or account.email)[0],
            profile_url=f"/people/{account.id}/",
        )
        for account in account_model.objects.filter(pk__in=account_ids)
    )


def test_like_is_unique_idempotent_and_counted_in_article_index() -> None:
    author = _account("like-author", roles=("AUTHOR", "ADMINISTRATOR"))
    member = _account("like-member")
    other = _account("like-other")
    article_id = _published_article(author, label="service")

    first = set_article_like(
        account_id=member.id,
        article_id=article_id,
        liked=True,
    )
    duplicate = set_article_like(
        account_id=member.id,
        article_id=article_id,
        liked=True,
    )
    set_article_like(account_id=other.id, article_id=article_id, liked=True)

    assert first.changed is True
    assert duplicate.changed is False
    assert is_article_liked(account_id=member.id, article_id=article_id) is True
    assert article_like_counts(article_ids=(article_id,)) == {article_id: 2}
    configure_profile_identity_collection_provider(_profile_identities)
    page = home_article_page(actor_id=member.id)
    assert page.items[0].article_id == article_id
    assert page.items[0].like_count == 2

    removed = set_article_like(
        account_id=member.id,
        article_id=article_id,
        liked=False,
    )
    repeated = set_article_like(
        account_id=member.id,
        article_id=article_id,
        liked=False,
    )
    assert removed.changed is True
    assert repeated.changed is False
    assert article_like_counts(article_ids=(article_id,)) == {article_id: 1}


def test_like_http_requires_login_and_reads_back_detail_state() -> None:
    author = _account("like-http-author", roles=("AUTHOR", "ADMINISTRATOR"))
    member = _account("like-http-member")
    article_id = _published_article(author, label="http")
    detail_url = reverse("article:detail", kwargs={"article_id": article_id})
    like_url = reverse("article:like", kwargs={"article_id": article_id})

    anonymous = Client(REMOTE_ADDR="127.0.0.1")
    page = anonymous.get(detail_url)
    assert page.status_code == 200
    assert "data-article-like-login" in page.content.decode()
    denied = anonymous.post(like_url, {"target_state": "liked"})
    assert denied.status_code == 302
    assert denied.url.startswith(reverse("accounts:login"))

    client = _logged_in_client(member)
    liked = client.post(
        like_url,
        {"target_state": "liked"},
        HTTP_HX_REQUEST="true",
    )
    assert liked.status_code == 200
    assert 'aria-pressed="true"' in liked.content.decode()
    assert 'data-like-count="1"' in liked.content.decode()

    refreshed = client.get(detail_url)
    assert refreshed.status_code == 200
    assert refreshed.context["like_is_saved"] is True
    assert refreshed.context["like_count"] == 1
    assert 'data-article-action="like"' in refreshed.content.decode()
