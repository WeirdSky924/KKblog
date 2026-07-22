from django.urls import include, path

from apps.core.errors.handlers import not_found, permission_denied, server_error

handler403 = permission_denied
handler404 = not_found
handler500 = server_error

urlpatterns = [
    path("", include("apps.operations.urls")),
]
