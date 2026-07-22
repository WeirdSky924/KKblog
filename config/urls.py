from django.urls import include, path

from apps.core.errors.handlers import not_found, permission_denied, server_error

handler403 = permission_denied
handler404 = not_found
handler500 = server_error

urlpatterns = [
    path("accounts/", include("apps.accounts.urls")),
    path("admin/", include("apps.administration.urls")),
    path("", include("apps.operations.urls")),
    path("", include("apps.discovery.urls")),
]
