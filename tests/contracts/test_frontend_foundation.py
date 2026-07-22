import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import Client, override_settings
from django.urls import path

from apps.core.errors import DomainError, ErrorCode
from apps.core.errors.handlers import not_found, permission_denied, server_error

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def internal_error(request):
    del request
    raise RuntimeError("password=frontend-private-sentinel")


def validation_error(request):
    del request
    raise DomainError(ErrorCode.VALIDATION_FAILED)


def ready(request):
    del request
    return HttpResponse("ready")


urlpatterns = [
    path("ready/", ready),
    path("error/422/", validation_error),
    path("error/500/", internal_error),
]
handler403 = permission_denied
handler404 = not_found
handler500 = server_error


@override_settings(ROOT_URLCONF=__name__)
def test_error_pages_use_safe_copy_shared_shell_and_recovery_controls() -> None:
    client = Client(raise_request_exception=False)

    not_found = client.get("/missing/")
    assert not_found.status_code == 404
    assert 'lang="zh-Hans"' in not_found.content.decode()
    assert 'id="global-feedback"' in not_found.content.decode()
    assert "页面没有找到" in not_found.content.decode()
    assert "data-error-back" in not_found.content.decode()

    server_error = client.get("/error/500/")
    body = server_error.content.decode()
    assert server_error.status_code == 500
    assert "页面暂时无法显示" in body
    assert "frontend-private-sentinel" not in body
    assert "data-error-retry" in body
    assert "data-trace-code" in body

    partial = client.get("/error/422/", HTTP_HX_REQUEST="true")
    assert partial.status_code == 422
    assert "data-error-focus" in partial.content.decode()
    assert 'id="global-feedback"' not in partial.content.decode()


def test_maintenance_template_is_noindex_and_has_honest_recovery() -> None:
    body = render_to_string("maintenance.html")
    assert "正在维护" in body
    assert "通过健康检查" in body
    assert 'name="robots" content="noindex,nofollow"' in body
    assert 'id="global-feedback"' in body
    assert "data-maintenance-retry" in body


def test_frontend_assets_and_production_fingerprints_are_wired() -> None:
    base = (PROJECT_ROOT / "templates/base.html").read_text(encoding="utf-8")
    package = (PROJECT_ROOT / "package.json").read_text(encoding="utf-8")
    production = (PROJECT_ROOT / "config/settings/production.py").read_text(
        encoding="utf-8"
    )

    assert "dist/theme.js" in base
    assert "dist/styles.css" in base
    assert "dist/app.js" in base
    assert '"code":"409|422","swap":true' in base
    assert '"lucide"' in package
    assert "ManifestStaticFilesStorage" in production


def test_collectstatic_writes_fingerprinted_build_files(tmp_path: Path) -> None:
    storages = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": (
                "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
            ),
        },
    }
    with override_settings(STATIC_ROOT=tmp_path, STORAGES=storages):
        call_command("collectstatic", interactive=False, verbosity=0)

    manifest = json.loads((tmp_path / "staticfiles.json").read_text(encoding="utf-8"))
    for source in ("dist/styles.css", "dist/theme.js", "dist/app.js"):
        fingerprinted = manifest["paths"][source]
        assert fingerprinted != source
        assert (tmp_path / fingerprinted).is_file()
    assert not any(path.startswith("src/") for path in manifest["paths"])


@pytest.mark.parametrize(
    "caddyfile,cache_policy",
    [
        ("Caddyfile.development", "no-cache"),
        ("Caddyfile.production", "immutable"),
    ],
)
def test_caddy_serves_only_built_static_assets(
    caddyfile: str, cache_policy: str
) -> None:
    source = (PROJECT_ROOT / "docker/caddy" / caddyfile).read_text(encoding="utf-8")
    assert "handle_path /static/*" in source
    assert "root * /srv/static" in source
    assert cache_policy in source
