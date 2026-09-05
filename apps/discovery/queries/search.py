from dataclasses import dataclass

from apps.core.pagination import page_window

from ..profile_identity import (
    ProfileIdentity,
    search_profile_identity_page,
)


@dataclass(frozen=True, slots=True)
class AuthorSearchPage:
    items: tuple[ProfileIdentity, ...]
    page_number: int
    page_size: int
    total_items: int
    total_pages: int
    has_previous: bool
    has_next: bool
    page_window: tuple[int | None, ...]


def author_search_page(
    *, query: str, page: int = 1, page_size: int = 20
) -> AuthorSearchPage:
    source = search_profile_identity_page(
        query=query,
        page=page,
        page_size=page_size,
    )
    return AuthorSearchPage(
        items=source.items,
        page_number=source.page_number,
        page_size=source.page_size,
        total_items=source.total_items,
        total_pages=source.total_pages,
        has_previous=source.has_previous,
        has_next=source.has_next,
        page_window=page_window(source.page_number, source.total_pages),
    )
