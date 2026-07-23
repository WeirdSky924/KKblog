from django.urls import path

from apps.discovery.views import article_placeholder

app_name = "article"

urlpatterns = [
    path("<str:article_id>/", article_placeholder, name="detail"),
]
