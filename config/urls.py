from django.urls import include, path

from apps.accounts.audit import configure_profile_audit_writer
from apps.accounts.public import PublicAccountNotFound, public_account_identity
from apps.core.errors.handlers import not_found, permission_denied, server_error
from apps.discovery.profile_identity import configure_profile_identity_provider
from apps.operations.public import record_audit_entry


def _public_profile_identity(account_id):
    try:
        return public_account_identity(account_id)
    except PublicAccountNotFound:
        return None


configure_profile_audit_writer(record_audit_entry)
configure_profile_identity_provider(_public_profile_identity)

handler403 = permission_denied
handler404 = not_found
handler500 = server_error

urlpatterns = [
    path("accounts/", include("apps.accounts.urls")),
    path("admin/", include("apps.administration.urls")),
    path("", include("apps.media.urls")),
    path("", include("apps.operations.urls")),
    path("", include("apps.discovery.urls")),
    path("articles/", include("apps.discovery.article_urls")),
]
