from django.urls import path

from apps.discovery.views import article_bookmark, article_detail

app_name = "article"

urlpatterns = [
    path("<str:article_id>/", article_detail, name="detail"),
    path("<str:article_id>/bookmark/", article_bookmark, name="bookmark"),
]
