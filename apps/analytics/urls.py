from django.urls import path

from apps.analytics.presentation.admin_view import internal_authorize

app_name = "analytics"

urlpatterns = [
    path(
        "internal/analytics/authorize",
        internal_authorize,
        name="internal-authorize",
    ),
]
