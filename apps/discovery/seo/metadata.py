from dataclasses import dataclass

from apps.content.public import sanitized_article_plain_text


@dataclass(frozen=True, slots=True)
class ArticleSeoMetadata:
    title: str
    description: str
    indexable: bool

    @property
    def robots(self) -> str:
        return "index,follow" if self.indexable else "noindex,nofollow"


def sanitized_plain_text(html: str) -> str:
    return sanitized_article_plain_text(html)


def article_seo_metadata(
    *, title: str, sanitized_body_html: str, indexable: bool
) -> ArticleSeoMetadata:
    if not isinstance(title, str) or not title:
        raise ValueError("article title is required")
    if type(indexable) is not bool:
        raise TypeError("indexable must be a boolean")
    return ArticleSeoMetadata(
        title=title,
        description=sanitized_plain_text(sanitized_body_html)[:100],
        indexable=indexable,
    )
