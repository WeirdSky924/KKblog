from django.urls import path

from apps.discovery.views import home, public_profile

app_name = "public"

urlpatterns = [
    path("", home, name="home"),
    path("people/<uuid:account_id>/", public_profile, name="profile"),
]
