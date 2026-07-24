from django.urls import path

from .action_views import (
    comment_replies,
    confirm_comment_delete,
    confirm_comment_reply,
    create_comment_reply,
    delete_comment,
)

app_name = "comments"

urlpatterns = [
    path(
        "comments/<str:root_id>/replies/",
        comment_replies,
        name="comment-replies",
    ),
    path(
        "comments/<str:comment_id>/reply/confirm/",
        confirm_comment_reply,
        name="comment-reply-confirm",
    ),
    path(
        "comments/<str:comment_id>/reply/",
        create_comment_reply,
        name="comment-reply",
    ),
    path(
        "comments/<str:comment_id>/delete/confirm/",
        confirm_comment_delete,
        name="comment-delete-confirm",
    ),
    path(
        "comments/<str:comment_id>/delete/",
        delete_comment,
        name="comment-delete",
    ),
]
