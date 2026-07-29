import pytest
from django.urls import reverse

from apps.core.events.models import OutboxEvent
from apps.exchange.models import ExportJob
from apps.notifications.models import Notification
from apps.operations.models import AuditEntry

from .conftest import IdentityMatrix

pytestmark = pytest.mark.django_db(transaction=True)

ADMIN_PAGES = (
    "admin:index",
    "admin:users",
    "admin:ip-blocks",
    "admin:articles",
    "admin:comments",
    "admin:reports",
    "admin:tags",
    "admin:sections",
    "admin:invites",
    "admin:notifications",
    "admin:navigation",
    "admin:site-settings",
    "admin:exchange",
    "admin:audit",
    "admin:errors",
    "admin:tasks",
    "admin:analytics",
)

AUTHOR_PAGES = (
    "authoring:articles",
    "authoring:create",
    "authoring:comments-buffer",
    "authoring:comments-article",
    "authoring:import",
)


def _side_effect_counts() -> tuple[int, int, int, int]:
    return (
        AuditEntry.objects.count(),
        OutboxEvent.objects.count(),
        ExportJob.objects.count(),
        Notification.objects.count(),
    )


def test_every_admin_page_rejects_non_admin_get_post_and_htmx_without_writes(
    identities: IdentityMatrix,
) -> None:
    before = _side_effect_counts()
    for route_name in ADMIN_PAGES:
        url = reverse(route_name)
        for identity in ("visitor", "user", "owner", "other_author"):
            client = identities.clients[identity]
            assert client.get(url).status_code == 403, (route_name, identity, "GET")
            assert client.get(url, HTTP_HX_REQUEST="true").status_code == 403, (
                route_name,
                identity,
                "HTMX GET",
            )
            assert client.post(url, {"action": "forged"}).status_code == 403, (
                route_name,
                identity,
                "POST",
            )
            assert (
                client.post(
                    url,
                    {"action": "forged"},
                    HTTP_HX_REQUEST="true",
                ).status_code
                == 403
            ), (route_name, identity, "HTMX POST")

    assert _side_effect_counts() == before


def test_administrator_can_reach_every_admin_page(
    identities: IdentityMatrix,
) -> None:
    client = identities.clients["admin"]
    for route_name in ADMIN_PAGES:
        response = client.get(reverse(route_name))
        assert response.status_code not in {403, 404}, route_name
        assert response.headers.get("Cache-Control") == "private, no-store"


def test_author_workspace_role_matrix_for_full_and_htmx_requests(
    identities: IdentityMatrix,
) -> None:
    for route_name in AUTHOR_PAGES:
        url = reverse(route_name)
        visitor = identities.clients["visitor"]
        full = visitor.get(url)
        assert full.status_code == 302, route_name
        assert full.url.startswith(reverse("accounts:login"))
        partial = visitor.get(url, HTTP_HX_REQUEST="true")
        assert partial.status_code == 204, route_name
        assert partial.headers["HX-Redirect"].startswith(reverse("accounts:login"))

        assert identities.clients["user"].get(url).status_code == 403, route_name
        assert (
            identities.clients["user"].get(url, HTTP_HX_REQUEST="true").status_code
            == 403
        ), route_name
        for allowed in ("owner", "other_author", "admin"):
            response = identities.clients[allowed].get(url)
            assert response.status_code == 200, (route_name, allowed)
            assert response.headers["Cache-Control"] == "private, no-store"


def test_personal_pages_require_login_but_accept_each_authenticated_role(
    identities: IdentityMatrix,
) -> None:
    routes = (
        "accounts:settings",
        "accounts:sessions",
        "notifications:list",
    )
    for route_name in routes:
        url = reverse(route_name)
        visitor = identities.clients["visitor"].get(url)
        assert visitor.status_code == 302, route_name
        assert visitor.url.startswith(reverse("accounts:login"))
        for identity in ("user", "owner", "other_author", "admin"):
            response = identities.clients[identity].get(url)
            assert response.status_code == 200, (route_name, identity)
            assert response.headers.get("Cache-Control") == "private, no-store"
