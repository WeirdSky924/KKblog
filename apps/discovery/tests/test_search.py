from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str, *, nickname: str, author: bool = True, active: bool = True):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
        nickname=nickname,
    )
    if author:
        role_model.objects.create(account=account, role="AUTHOR")
    if not active:
        account.status = "DISABLED"
        account.save(update_fields=("status", "updated_at"))
    return account


def test_author_suggestions_match_one_character_and_enforce_public_boundaries(
    client,
) -> None:
    account = _account("kaj", nickname="Kaj")
    for nickname in ("Kaja", "Kaje", "Kaji", "Kajo", "Kaju", "Kaya"):
        _account(nickname.casefold(), nickname=nickname)
    _account("reader", nickname="Kite", author=False)
    _account("disabled", nickname="Kale", active=False)

    session_model = apps.get_model("accounts", "LoginSession")
    raw_token, _ = session_model.issue(account=account, remember=False)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = raw_token
    response = client.get("/search/suggestions/", {"type": "author", "q": "K"})
    payload = response.json()
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert len(payload["items"]) == 5
    assert payload["items"][0]["label"] == "Kaj"
    assert payload["items"][0]["url"].startswith("/people/")
    assert all(item["label"] not in {"Kite", "Kale"} for item in payload["items"])


def test_author_search_submission_renders_matching_public_profiles(client) -> None:
    visible = _account("profile", nickname="Kaj")
    hidden = _account("hidden", nickname="Kale", active=False)

    response = client.get("/search/", {"type": "author", "q": "K"})
    body = response.content.decode()

    assert response.status_code == 200
    assert "搜索作者" in body
    assert visible.nickname in body
    assert str(visible.id) in body
    assert hidden.nickname not in body


def test_empty_suggestion_query_is_a_stable_empty_state(client) -> None:
    response = client.get("/search/suggestions/", {"type": "article", "q": ""})

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_anonymous_search_never_returns_instant_suggestions(client) -> None:
    _account("kaj-anonymous", nickname="Kaj")

    response = client.get("/search/suggestions/", {"type": "author", "q": "K"})

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_article_suggestions_include_section_and_tags(client, monkeypatch) -> None:
    account = _account("article-suggestion", nickname="Kaj")
    session_model = apps.get_model("accounts", "LoginSession")
    raw_token, _ = session_model.issue(account=account, remember=False)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = raw_token
    monkeypatch.setattr(
        "apps.discovery.views.search_visible_titles",
        lambda **_kwargs: SimpleNamespace(
            items=(
                SimpleNamespace(
                    article_id="01KTESTARTICLE0000000000000",
                    author_id=account.id,
                    title="测试文章",
                    section_name="学习记录",
                    tags=(
                        SimpleNamespace(name="Python"),
                        SimpleNamespace(name="Django"),
                    ),
                ),
            )
        ),
    )

    response = client.get("/search/suggestions/", {"type": "article", "q": "测试"})

    assert response.status_code == 200
    assert response.json()["items"][0]["section"] == "学习记录"
    assert response.json()["items"][0]["tags"] == ["Python", "Django"]
