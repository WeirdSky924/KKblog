from django.urls import path

from apps.authoring.presentation.article_views import articles
from apps.authoring.presentation.editor_views import (
    create,
    discard_draft,
    edit,
    preview,
)

app_name = "authoring"

urlpatterns = [
    path("articles/", articles, name="articles"),
    path("articles/new/", create, name="create"),
    path("articles/preview/", preview, name="preview"),
    path("articles/<str:article_id>/edit/", edit, name="edit"),
    path(
        "articles/<str:article_id>/draft/discard/",
        discard_draft,
        name="discard-draft",
    ),
]
