from django.urls import path

from apps.discovery.views import home, public_profile, search

app_name = "public"

urlpatterns = [
    path("", home, name="home"),
    path("search/", search, name="search"),
    path("people/<uuid:account_id>/", public_profile, name="profile"),
]
