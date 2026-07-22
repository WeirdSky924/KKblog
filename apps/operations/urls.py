from django.urls import path

from apps.operations.presentation.health import live, ready

app_name = "operations"

urlpatterns = [
    path("health/live", live, name="live"),
    path("health/ready", ready, name="ready"),
]
