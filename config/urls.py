from django.urls import include, path

from apps.accounts.audit import configure_profile_audit_writer
from apps.accounts.public import PublicAccountNotFound, public_account_identity
from apps.core.errors.handlers import not_found, permission_denied, server_error
from apps.core.errors.runtime_sink import configure_runtime_error_sink
from apps.discovery.profile_identity import configure_profile_identity_provider
from apps.operations.public import capture_runtime_error, record_audit_entry
from config.comment_integrations import configure_comment_integrations
from config.moderation_integrations import configure_moderation_integrations
from config.navigation_integrations import configure_navigation_integrations


def _public_profile_identity(account_id):
    try:
        return public_account_identity(account_id)
    except PublicAccountNotFound:
        return None


configure_profile_audit_writer(record_audit_entry)
configure_runtime_error_sink(capture_runtime_error)
configure_profile_identity_provider(_public_profile_identity)
configure_comment_integrations()
configure_moderation_integrations()
configure_navigation_integrations()

handler403 = permission_denied
handler404 = not_found
handler500 = server_error

urlpatterns = [
    path("accounts/", include("config.account_urls")),
    path("", include("apps.analytics.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("author/", include("apps.authoring.urls")),
    path("admin/", include("apps.administration.urls")),
    path("", include("apps.media.urls")),
    path("", include("apps.operations.urls")),
    path("", include("apps.comments.urls")),
    path("", include("apps.moderation.urls")),
    path("", include("apps.discovery.urls")),
    path("articles/", include("apps.discovery.article_urls")),
]
