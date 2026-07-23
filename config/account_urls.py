from django.urls import path

from apps.accounts.urls import urlpatterns as account_urlpatterns
from apps.discovery.views import bookmarks

app_name = "accounts"

urlpatterns = [
    *account_urlpatterns,
    path("bookmarks/", bookmarks, name="bookmarks"),
]
