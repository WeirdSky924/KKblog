from django.urls import path

from apps.discovery.views import home

app_name = "public"

urlpatterns = [path("", home, name="home")]
