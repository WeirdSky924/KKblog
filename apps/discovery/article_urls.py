from django.urls import path

from apps.comments.views import create_article_comment, upload_article_comment_image
from apps.discovery.views import article_bookmark, article_detail

app_name = "article"

urlpatterns = [
    path("<str:article_id>/", article_detail, name="detail"),
    path("<str:article_id>/bookmark/", article_bookmark, name="bookmark"),
    path(
        "<str:article_id>/comments/",
        create_article_comment,
        name="comment-create",
    ),
    path(
        "<str:article_id>/comment-images/",
        upload_article_comment_image,
        name="comment-image",
    ),
]
