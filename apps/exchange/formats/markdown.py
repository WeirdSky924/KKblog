from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

from apps.core.ids import normalize_ulid

from .front_matter import FrontMatterError, split_front_matter

_MARKDOWN = MarkdownIt("commonmark", {"html": True})


class MarkdownParseError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class MarkdownDocument:
    metadata: dict[str, object]
    body: str
    title: str
    imported_article_id: str | None
    local_image_paths: tuple[str, ...]
    body_image_paths: tuple[str, ...]
    cover_image_path: str | None
    preview_html: str


MarkdownRenderer = Callable[[str], str]


def _title_from_heading(body: str) -> str | None:
    tokens = _MARKDOWN.parse(body)
    for index, token in enumerate(tokens[:-1]):
        if token.type == "heading_open" and token.tag == "h1":
            candidate = tokens[index + 1]
            if candidate.type == "inline":
                title = candidate.content.strip()
                if title:
                    return title
    return None


def _local_image_path(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
    except ValueError:
        raise MarkdownParseError("exchange.import_image_path_invalid.v1") from None
    if parsed.scheme in {"http", "https", "mailto", "media"} or parsed.netloc:
        return None
    if parsed.scheme:
        return None
    raw = unquote(parsed.path).replace("\\", "/")
    path = PurePosixPath(raw)
    windows = PureWindowsPath(raw)
    if (
        not raw
        or raw.startswith("/")
        or path.is_absolute()
        or windows.drive
        or windows.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise MarkdownParseError("exchange.import_image_path_invalid.v1")
    return path.as_posix()


def _image_paths(
    body: str, metadata: dict[str, object]
) -> tuple[tuple[str, ...], str | None]:
    paths: list[str] = []
    for token in _MARKDOWN.parse(body):
        for candidate in token.children or (token,):
            if candidate.type != "image":
                continue
            source = candidate.attrGet("src")
            if not isinstance(source, str):
                raise MarkdownParseError("exchange.import_image_path_invalid.v1")
            local = _local_image_path(source)
            if local is not None:
                paths.append(local)
    body_paths = tuple(dict.fromkeys(paths))
    cover_path = None
    cover = metadata.get("cover")
    if cover is not None:
        if not isinstance(cover, str):
            raise MarkdownParseError("exchange.front_matter_invalid.v1")
        cover_path = _local_image_path(cover)
    return body_paths, cover_path


def parse_markdown(
    source: str,
    *,
    item_path: str,
    body_max_bytes: int,
    renderer: MarkdownRenderer,
) -> MarkdownDocument:
    try:
        metadata, body = split_front_matter(source)
    except FrontMatterError:
        raise MarkdownParseError("exchange.front_matter_invalid.v1") from None
    if len(body.encode("utf-8")) > body_max_bytes:
        raise MarkdownParseError("exchange.import_body_too_large.v1")
    title_value = metadata.get("title")
    if title_value is not None and not isinstance(title_value, str):
        raise MarkdownParseError("exchange.front_matter_invalid.v1")
    title = (
        title_value or _title_from_heading(body) or PurePosixPath(item_path).stem
    ).strip()
    if not title or len(title) > 30:
        raise MarkdownParseError("exchange.import_title_invalid.v1")
    imported_id = metadata.get("id")
    if imported_id is not None:
        if not isinstance(imported_id, str):
            raise MarkdownParseError("exchange.front_matter_invalid.v1")
        try:
            imported_id = normalize_ulid(imported_id)
        except (TypeError, ValueError):
            raise MarkdownParseError("exchange.import_id_invalid.v1") from None
        metadata["id"] = imported_id
    for field in ("visibility", "summary_mode", "status"):
        value = metadata.get(field)
        if isinstance(value, str):
            metadata[field] = value.upper()
    try:
        rendered = renderer(body)
    except (TypeError, ValueError):
        raise MarkdownParseError("exchange.import_markdown_invalid.v1") from None
    if not isinstance(rendered, str):
        raise TypeError("Markdown renderer must return sanitized HTML")
    body_image_paths, cover_image_path = _image_paths(body, metadata)
    return MarkdownDocument(
        metadata=metadata,
        body=body,
        title=title,
        imported_article_id=imported_id,
        local_image_paths=tuple(
            dict.fromkeys(
                (*body_image_paths, *((cover_image_path,) if cover_image_path else ()))
            )
        ),
        body_image_paths=body_image_paths,
        cover_image_path=cover_image_path,
        preview_html=rendered,
    )
