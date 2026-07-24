from django.urls import path

from apps.discovery.seo import public_sitemap
from apps.discovery.views import home, public_profile, search, section, tag

app_name = "public"

urlpatterns = [
    path("", home, name="home"),
    path("sitemap.xml", public_sitemap, name="sitemap"),
    path("sections/<uuid:section_id>/", section, name="section"),
    path("tags/<uuid:tag_id>/", tag, name="tag"),
    path("search/", search, name="search"),
    path("people/<uuid:account_id>/", public_profile, name="profile"),
]
