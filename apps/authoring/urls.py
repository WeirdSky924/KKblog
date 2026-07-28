from django.urls import path

from apps.authoring.presentation.article_views import articles
from apps.authoring.presentation.comment_views import (
    comments_article_page,
    comments_article_replies,
    comments_articles,
    comments_buffer,
    delete_managed_comment,
    toggle_article_comments,
)
from apps.authoring.presentation.editor_views import (
    create,
    discard_draft,
    edit,
    preview,
    resolve_conflict,
)
from apps.authoring.presentation.import_views import (
    confirm_import_job,
    import_job,
    import_job_status,
    import_workspace,
    update_import_item,
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
    path("comments/buffer/", comments_buffer, name="comments-buffer"),
    path("comments/articles/", comments_articles, name="comments-article"),
    path(
        "comments/articles/<str:article_id>/page/",
        comments_article_page,
        name="comments-article-page",
    ),
    path(
        "comments/articles/<str:article_id>/replies/<str:root_id>/",
        comments_article_replies,
        name="comments-article-replies",
    ),
    path(
        "comments/articles/<str:article_id>/settings/",
        toggle_article_comments,
        name="comments-settings",
    ),
    path(
        "comments/articles/<str:article_id>/<str:comment_id>/delete/",
        delete_managed_comment,
        name="comments-delete",
    ),
    path("import/", import_workspace, name="import"),
    path("import/<str:job_id>/", import_job, name="import-job"),
    path(
        "import/<str:job_id>/status/",
        import_job_status,
        name="import-status",
    ),
    path(
        "import/<str:job_id>/items/<str:item_id>/",
        update_import_item,
        name="import-item",
    ),
    path(
        "import/<str:job_id>/confirm/",
        confirm_import_job,
        name="import-confirm",
    ),
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
