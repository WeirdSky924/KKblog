from django.urls import path

from apps.media.presentation.delivery_views import internal_authorize
from apps.media.presentation.upload_views import upload_avatar, upload_for_adapter

app_name = "media"

urlpatterns = [
    path("media/uploads/avatar/", upload_avatar, name="upload-avatar"),
    path("media/picker-uploads/<slug:adapter>/", upload_for_adapter, name="upload"),
    path("internal/media/authorize", internal_authorize, name="internal-authorize"),
]
