from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from uuid import UUID

from django.conf import settings
from redis import Redis

from apps.content.public import (
    VisibleArticleItem,
    VisibleArticlePage,
    VisibleArticleTag,
)
from apps.core.ids import normalize_ulid

from .keys import (
    article_cache_key,
    article_generation_key,
    cache_namespace,
    list_cache_key,
    list_generation_key,
)


def _integer(value, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError("cached integer is invalid")
    return value


def _text(value, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ValueError("cached text is invalid")
    return value


def _datetime(value) -> datetime:
    if not isinstance(value, str):
        raise ValueError("cached datetime is invalid")
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("cached datetime is invalid") from None
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("cached datetime is invalid")
    return result


def _exact_mapping(value, fields: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("cached object shape is invalid")
    return value


def _tag_from_payload(value) -> VisibleArticleTag:
    item = _exact_mapping(value, {"id", "name", "state"})
    return VisibleArticleTag(
        tag_id=UUID(str(item["id"])),
        name=str(_text(item["name"])),
        state=str(_text(item["state"])),
    )


def _item_from_payload(value) -> VisibleArticleItem:
    item = _exact_mapping(
        value,
        {
            "article_id",
            "revision_id",
            "author_id",
            "title",
            "summary",
            "visibility",
            "section_id",
            "section_name",
            "tags",
            "cover_asset_id",
            "published_at",
        },
    )
    if item["visibility"] != "PUBLIC" or not isinstance(item["tags"], list):
        raise ValueError("cached public article is invalid")
    section_id = item["section_id"]
    section_name = _text(item["section_name"], optional=True)
    if (section_id is None) != (section_name is None):
        raise ValueError("cached section is invalid")
    cover_asset_id = item["cover_asset_id"]
    return VisibleArticleItem(
        article_id=normalize_ulid(item["article_id"]),
        revision_id=normalize_ulid(item["revision_id"]),
        author_id=UUID(str(item["author_id"])),
        title=str(_text(item["title"])),
        summary=_text(item["summary"], optional=True),
        visibility="PUBLIC",
        section_id=UUID(str(section_id)) if section_id is not None else None,
        section_name=section_name,
        tags=tuple(_tag_from_payload(tag) for tag in item["tags"]),
        cover_asset_id=(
            normalize_ulid(cover_asset_id) if cover_asset_id is not None else None
        ),
        published_at=_datetime(item["published_at"]),
    )


def _page_from_payload(raw: str) -> VisibleArticlePage | None:
    try:
        value = json.loads(raw)
        page = _exact_mapping(
            value,
            {
                "version",
                "items",
                "page_number",
                "page_size",
                "total_items",
                "total_pages",
                "has_previous",
                "has_next",
            },
        )
        if page["version"] != 2 or not isinstance(page["items"], list):
            raise ValueError("cached page is invalid")
        if type(page["has_previous"]) is not bool or type(page["has_next"]) is not bool:
            raise ValueError("cached page flags are invalid")
        return VisibleArticlePage(
            items=tuple(_item_from_payload(item) for item in page["items"]),
            page_number=_integer(page["page_number"], minimum=1),
            page_size=_integer(page["page_size"], minimum=1),
            total_items=_integer(page["total_items"]),
            total_pages=_integer(page["total_pages"], minimum=1),
            has_previous=page["has_previous"],
            has_next=page["has_next"],
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _page_payload(page: VisibleArticlePage) -> str:
    items = []
    for item in page.items:
        if item.visibility != "PUBLIC":
            raise ValueError("only public list items may be cached")
        items.append(
            {
                "article_id": item.article_id,
                "revision_id": item.revision_id,
                "author_id": str(item.author_id),
                "title": item.title,
                "summary": item.summary,
                "visibility": item.visibility,
                "section_id": str(item.section_id) if item.section_id else None,
                "section_name": item.section_name,
                "tags": [
                    {"id": str(tag.tag_id), "name": tag.name, "state": tag.state}
                    for tag in item.tags
                ],
                "cover_asset_id": item.cover_asset_id,
                "published_at": item.published_at.isoformat(),
            }
        )
    return json.dumps(
        {
            "version": 2,
            "items": items,
            "page_number": page.page_number,
            "page_size": page.page_size,
            "total_items": page.total_items,
            "total_pages": page.total_pages,
            "has_previous": page.has_previous,
            "has_next": page.has_next,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


class RedisDiscoveryCache:
    def __init__(
        self,
        client: Redis,
        *,
        namespace: str,
        article_ttl_seconds: int,
        list_ttl_seconds: int,
    ) -> None:
        self.client = client
        self.namespace = cache_namespace(namespace)
        self.article_ttl_seconds = _integer(article_ttl_seconds, minimum=1)
        self.list_ttl_seconds = _integer(list_ttl_seconds, minimum=1)

    def _generation(self, key: str) -> int:
        value = self.client.get(key)
        if value is None:
            return 0
        try:
            return _integer(int(value))
        except (TypeError, ValueError):
            return 0

    def article_generation(self, article_id: str) -> int:
        return self._generation(article_generation_key(self.namespace, article_id))

    def list_generation(self) -> int:
        return self._generation(list_generation_key(self.namespace))

    def get_article_body(
        self,
        *,
        article_id: str,
        revision_id: str,
        sanitizer_version: str,
        generation: int | None = None,
    ) -> str | None:
        active_generation = (
            self.article_generation(article_id) if generation is None else generation
        )
        key = article_cache_key(
            self.namespace,
            article_id=article_id,
            revision_id=revision_id,
            sanitizer_version=sanitizer_version,
            generation=active_generation,
        )
        raw = self.client.get(key)
        if raw is None or active_generation != self.article_generation(article_id):
            return None
        try:
            value = _exact_mapping(json.loads(raw), {"version", "html"})
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return (
            value["html"]
            if value["version"] == 1 and isinstance(value["html"], str)
            else None
        )

    def set_article_body(
        self,
        *,
        article_id: str,
        revision_id: str,
        sanitizer_version: str,
        html: str,
        expected_generation: int | None = None,
    ) -> bool:
        generation = self.article_generation(article_id)
        if expected_generation is not None and generation != expected_generation:
            return False
        key = article_cache_key(
            self.namespace,
            article_id=article_id,
            revision_id=revision_id,
            sanitizer_version=sanitizer_version,
            generation=generation,
        )
        payload = json.dumps(
            {"version": 1, "html": html},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        self.client.setex(key, self.article_ttl_seconds, payload)
        return True

    def get_list(
        self, *, query_hash: str, generation: int | None = None
    ) -> VisibleArticlePage | None:
        active_generation = self.list_generation() if generation is None else generation
        key = list_cache_key(
            self.namespace, query_hash=query_hash, generation=active_generation
        )
        raw = self.client.get(key)
        if raw is None or active_generation != self.list_generation():
            return None
        return _page_from_payload(raw)

    def set_list(
        self,
        *,
        query_hash: str,
        page: VisibleArticlePage,
        expected_generation: int | None = None,
    ) -> bool:
        generation = self.list_generation()
        if expected_generation is not None and generation != expected_generation:
            return False
        key = list_cache_key(
            self.namespace, query_hash=query_hash, generation=generation
        )
        self.client.setex(key, self.list_ttl_seconds, _page_payload(page))
        return True

    def invalidate(self, *, article_ids=(), lists: bool = True) -> None:
        pipeline = self.client.pipeline(transaction=True)
        if lists:
            pipeline.incr(list_generation_key(self.namespace))
        for article_id in tuple(dict.fromkeys(article_ids)):
            pipeline.incr(article_generation_key(self.namespace, article_id))
        pipeline.execute()


@lru_cache(maxsize=8)
def _configured_cache(
    redis_url: str,
    namespace: str,
    article_ttl_seconds: int,
    list_ttl_seconds: int,
) -> RedisDiscoveryCache:
    client = Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    return RedisDiscoveryCache(
        client,
        namespace=namespace,
        article_ttl_seconds=article_ttl_seconds,
        list_ttl_seconds=list_ttl_seconds,
    )


def default_discovery_cache() -> RedisDiscoveryCache | None:
    redis_url = getattr(settings, "REDIS_URL", "")
    if not redis_url:
        return None
    return _configured_cache(
        redis_url,
        getattr(settings, "DISCOVERY_CACHE_NAMESPACE", "kaj"),
        getattr(settings, "DISCOVERY_ARTICLE_CACHE_TTL_SECONDS", 3_600),
        getattr(settings, "DISCOVERY_LIST_CACHE_TTL_SECONDS", 60),
    )
