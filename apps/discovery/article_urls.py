from django.urls import path

from apps.comments.views import (
    article_comment_page,
    article_comment_replies,
    confirm_article_comment_delete,
    create_article_comment,
    delete_article_comment,
    pin_article_comment,
    upload_article_comment_image,
)
from apps.discovery.views import (
    article_bookmark,
    article_detail,
    article_like,
    article_reading_bookmark,
)

app_name = "article"

urlpatterns = [
    path("<str:article_id>/", article_detail, name="detail"),
    path("<str:article_id>/bookmark/", article_bookmark, name="bookmark"),
    path("<str:article_id>/like/", article_like, name="like"),
    path(
        "<str:article_id>/reading-bookmark/",
        article_reading_bookmark,
        name="reading-bookmark",
    ),
    path(
        "<str:article_id>/comments/",
        create_article_comment,
        name="comment-create",
    ),
    path(
        "<str:article_id>/comments/page/",
        article_comment_page,
        name="comment-page",
    ),
    path(
        "<str:article_id>/comments/<str:root_id>/replies/",
        article_comment_replies,
        name="comment-replies",
    ),
    path(
        "<str:article_id>/comments/<str:comment_id>/delete/confirm/",
        confirm_article_comment_delete,
        name="comment-delete-confirm",
    ),
    path(
        "<str:article_id>/comments/<str:comment_id>/delete/",
        delete_article_comment,
        name="comment-delete",
    ),
    path(
        "<str:article_id>/comments/<str:comment_id>/pin/",
        pin_article_comment,
        name="comment-pin",
    ),
    path(
        "<str:article_id>/comment-images/",
        upload_article_comment_image,
        name="comment-image",
    ),
]
