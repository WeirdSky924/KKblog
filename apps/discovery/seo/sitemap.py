from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps.views import sitemap
from django.urls import reverse

from apps.content.public import public_article_sitemap_items


class PublicArticleSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return public_article_sitemap_items()

    def location(self, item) -> str:
        return reverse("article:detail", kwargs={"article_id": item.article_id})

    def lastmod(self, item):
        return item.last_modified_at


PUBLIC_SITEMAPS = {"articles": PublicArticleSitemap}


def public_sitemap(request):
    response = sitemap(request, sitemaps=PUBLIC_SITEMAPS)
    response.headers["Cache-Control"] = "no-store"
    return response
