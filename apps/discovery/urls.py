from django.urls import path

from apps.comments.guestbook_views import (
    create_guestbook_comment,
    guestbook_comment_page,
    guestbook_page,
    upload_guestbook_comment_image,
)
from apps.discovery.seo import public_sitemap
from apps.discovery.views import home, public_profile, search, section, tag

app_name = "public"

urlpatterns = [
    path("", home, name="home"),
    path("guestbook/", guestbook_page, name="guestbook"),
    path(
        "guestbook/comments/",
        create_guestbook_comment,
        name="guestbook-comment-create",
    ),
    path(
        "guestbook/comments/page/",
        guestbook_comment_page,
        name="guestbook-comment-page",
    ),
    path(
        "guestbook/comment-images/",
        upload_guestbook_comment_image,
        name="guestbook-comment-image",
    ),
    path("sitemap.xml", public_sitemap, name="sitemap"),
    path("sections/<uuid:section_id>/", section, name="section"),
    path("tags/<uuid:tag_id>/", tag, name="tag"),
    path("search/", search, name="search"),
    path("people/<uuid:account_id>/", public_profile, name="profile"),
]
