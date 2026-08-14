from django.urls import path

from .views import opportunities, opportunity_bookmark

app_name = "opportunities"

urlpatterns = [
    path("", opportunities, name="index"),
    path("bookmark/", opportunity_bookmark, name="bookmark"),
]
