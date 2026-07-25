from django.urls import path

from apps.notifications.views import inbox, mark_all_read, open_notification, popover

app_name = "notifications"

urlpatterns = [
    path("", inbox, name="list"),
    path("popover/", popover, name="popover"),
    path("read-all/", mark_all_read, name="mark-all-read"),
    path("<str:notification_id>/open/", open_notification, name="open"),
]
