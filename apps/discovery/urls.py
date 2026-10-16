from django.urls import path

from apps.comments.guestbook_views import (
    create_guestbook_board_comment,
    create_guestbook_comment,
    guestbook_board_page,
    guestbook_comment_page,
    guestbook_page,
    upload_guestbook_comment_image,
)
from apps.discovery.seo import public_sitemap
from apps.discovery.views import (
    home,
    public_profile,
    search,
    search_suggestions,
    section,
    tag,
)
from apps.navigation.presentation.public import (
    about_page,
    friend_links_page,
    privacy_page,
    terms_page,
)

app_name = "public"

urlpatterns = [
    path("", home, name="home"),
    path("about/", about_page, name="about"),
    path("friend-links/", friend_links_page, name="friend-links"),
    path("privacy/", privacy_page, name="privacy"),
    path("terms/", terms_page, name="terms"),
    path("guestbook/", guestbook_page, name="guestbook"),
    path(
        "guestbook/comments/",
        create_guestbook_comment,
        name="guestbook-comment-create",
    ),
    path(
        "guestbook/board/comments/",
        create_guestbook_board_comment,
        name="guestbook-board-comment-create",
    ),
    path(
        "guestbook/comments/page/",
        guestbook_comment_page,
        name="guestbook-comment-page",
    ),
    path(
        "guestbook/board/",
        guestbook_board_page,
        name="guestbook-board-page",
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
    path("search/suggestions/", search_suggestions, name="search-suggestions"),
    path("people/<uuid:account_id>/", public_profile, name="profile"),
]
