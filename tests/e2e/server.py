import os
import sys
import types

sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

import django
from django.conf import settings
from django.core.management import execute_from_command_line
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import clear_url_caches, path

from apps.core.errors import DomainError, ErrorCode
from apps.core.errors.codes import spec_for
from apps.core.errors.handlers import (
    not_found,
    permission_denied,
    render_error_response,
    server_error,
)

django.setup()


def ready(request):
    del request
    return HttpResponse(
        '<!doctype html><html lang="zh-Hans"><head>'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="htmx-config" content=\''
        '{"responseHandling":[{"code":"204","swap":false},'
        '{"code":"[23]..","swap":true},'
        '{"code":"409|422","swap":true,"error":false},'
        '{"code":"[45]..","swap":false,"error":true}]}'
        "'>"
        '<link rel="icon" href="data:,">'
        '<script src="/static/dist/theme.js"></script>'
        '<link rel="stylesheet" href="/static/dist/styles.css">'
        '<script type="module" src="/static/dist/app.js"></script>'
        '</head><body><main class="site-main">'
        '<h1>验收入口</h1><div class="status-actions">'
        '<a id="error-page-trigger" class="button button--primary" '
        'data-error-origin href="/error/500/">打开错误页</a>'
        '<button class="button button--secondary" type="button" '
        'hx-get="/error/422/" hx-target="#partial-target">打开表单错误</button>'
        '</div><div id="partial-target"></div>'
        "</main></body></html>"
    )


def validation_error(request):
    del request
    raise DomainError(ErrorCode.VALIDATION_FAILED)


def internal_error(request):
    del request
    raise RuntimeError(
        "password=e2e-private verification_code=123456 "
        "Cookie=e2e-private DATABASE_URL=postgresql://user:private@db/kaj "
        "body=e2e-private"
    )


def long_error(request):
    request.trace_code = f"trc_{'a' * 180}"
    return render_error_response(request, spec_for(ErrorCode.INTERNAL_ERROR))


def maintenance(request):
    return render(request, "maintenance.html", status=503)


def feedback(request):
    return render(
        request,
        "base.html",
        {"feedback_items": [{"level": "success", "message": "设置已保存。"}]},
    )


urlconf = types.ModuleType("kaj_e2e_urls")
urlconf.urlpatterns = [
    path("ready/", ready),
    path("error/422/", validation_error),
    path("error/500/", internal_error),
    path("error/long/", long_error),
    path("maintenance/", maintenance),
    path("feedback/", feedback),
]
urlconf.handler403 = permission_denied
urlconf.handler404 = not_found
urlconf.handler500 = server_error
sys.modules[urlconf.__name__] = urlconf

settings.DEBUG = False
settings.ROOT_URLCONF = urlconf.__name__
clear_url_caches()

execute_from_command_line(
    ["manage.py", "runserver", "127.0.0.1:8766", "--noreload", "--insecure"]
)
