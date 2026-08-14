from datetime import datetime

from ..models import Article, ArticlePublication, ArticleRevision
from ..queries.publication_history import publication_history_schema_ready


def record_article_publication(
    *,
    article: Article,
    revision: ArticleRevision,
    published_at: datetime,
) -> None:
    if not publication_history_schema_ready():
        return
    ArticlePublication.objects.get_or_create(
        article=article,
        revision=revision,
        defaults={"published_at": published_at},
    )


__all__ = ["record_article_publication"]
