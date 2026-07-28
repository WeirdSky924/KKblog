from django.urls import path

from apps.authoring.presentation.article_views import articles
from apps.authoring.presentation.editor_views import (
    create,
    discard_draft,
    edit,
    preview,
    resolve_conflict,
)
from apps.authoring.presentation.publication_views import (
    cancel_article_schedule,
    publication_result,
    restore_version,
    review,
    versions,
)

app_name = "authoring"

urlpatterns = [
    path("articles/", articles, name="articles"),
    path("articles/new/", create, name="create"),
    path("articles/preview/", preview, name="preview"),
    path("articles/<str:article_id>/edit/", edit, name="edit"),
    path("articles/<str:article_id>/review/", review, name="review"),
    path("articles/<str:article_id>/versions/", versions, name="versions"),
    path(
        "articles/<str:article_id>/versions/restore/",
        restore_version,
        name="restore-version",
    ),
    path(
        "articles/<str:article_id>/publication/result/",
        publication_result,
        name="publication-result",
    ),
    path(
        "articles/<str:article_id>/schedule/cancel/",
        cancel_article_schedule,
        name="cancel-schedule",
    ),
    path(
        "articles/<str:article_id>/conflict/resolve/",
        resolve_conflict,
        name="resolve-conflict",
    ),
    path(
        "articles/<str:article_id>/draft/discard/",
        discard_draft,
        name="discard-draft",
    ),
]
