from django.http import HttpResponse
from django.test import Client, override_settings
from django.urls import path


def write_probe(request):
    del request
    return HttpResponse("ok")


def error_probe(request):
    del request
    raise RuntimeError("password=http-security-private-sentinel")


urlpatterns = [
    path("_test/write/", write_probe),
    path("_test/error/", error_probe),
]


@override_settings(ROOT_URLCONF=__name__)
def test_csrf_middleware_rejects_missing_token_and_accepts_matching_token() -> None:
    client = Client(enforce_csrf_checks=True)
    rejected = client.post("/_test/write/")
    assert rejected.status_code == 403
    assert rejected.headers["X-Frame-Options"] == "DENY"

    token = "A" * 32
    client.cookies["csrftoken"] = token
    accepted = client.post("/_test/write/", HTTP_X_CSRFTOKEN=token)
    assert accepted.status_code == 200
    assert accepted.headers["X-Frame-Options"] == "DENY"


@override_settings(
    ROOT_URLCONF=__name__,
    SECURE_CONTENT_TYPE_NOSNIFF=True,
)
def test_security_headers_apply_to_unified_internal_error() -> None:
    response = Client(raise_request_exception=False).get("/_test/error/")
    assert response.status_code == 500
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"
    assert b"http-security-private-sentinel" not in response.content
