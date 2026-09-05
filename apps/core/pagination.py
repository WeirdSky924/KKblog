"""Small, framework-neutral helpers shared by numbered collection pages."""

from __future__ import annotations

from dataclasses import dataclass


def page_window(current: int, total: int) -> tuple[int | None, ...]:
    """Return an elided page-number window for the shared pagination partial."""
    current = max(1, int(current))
    total = max(1, int(total))
    visible = {
        1,
        total,
        *(range(max(1, current - 2), min(total, current + 2) + 1)),
    }
    ordered = sorted(number for number in visible if 1 <= number <= total)
    result: list[int | None] = []
    previous = 0
    for number in ordered:
        if previous and number - previous > 1:
            result.append(None)
        result.append(number)
        previous = number
    return tuple(result)


@dataclass(frozen=True, slots=True)
class PageSlice[T]:
    """A small DTO for lists that use the shared numbered pagination UI."""

    items: tuple[T, ...]
    page_number: int
    page_size: int
    total_items: int
    total_pages: int
    has_previous: bool
    has_next: bool

    @property
    def page_window(self) -> tuple[int | None, ...]:
        return page_window(self.page_number, self.total_pages)


__all__ = ["PageSlice", "page_window"]
