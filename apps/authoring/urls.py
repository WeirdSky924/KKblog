from django.urls import path

from apps.authoring.presentation.article_views import articles

app_name = "authoring"

urlpatterns = [
    path("articles/", articles, name="articles"),
]
