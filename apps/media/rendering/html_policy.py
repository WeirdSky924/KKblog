from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit

import nh3

from apps.core.ids import normalize_ulid

from .embeds import TrustedEmbedPolicy, configured_trusted_embed_policy

SANITIZER_VERSION = "kaj-html-v2"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_CANDIDATE_BYTES = 8 * MAX_SOURCE_BYTES

_ALLOWED_TAGS = {
    "a",
    "abbr",
    "b",
    "blockquote",
    "br",
    "code",
    "del",
    "details",
    "div",
    "em",
    "figcaption",
    "figure",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "kaj-embed",
    "kbd",
    "li",
    "mark",
    "ol",
    "p",
    "pre",
    "s",
    "strong",
    "sub",
    "summary",
    "sup",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}
_CLEAN_CONTENT_TAGS = {
    "embed",
    "form",
    "iframe",
    "math",
    "noscript",
    "object",
    "script",
    "style",
    "svg",
    "template",
}
_ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"alt", "src", "title"},
    "kaj-embed": {"data-source", "data-url"},
    "ol": {"start"},
}
_VOID_TAGS = {"br", "hr", "img"}


class RenderingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RenderedContent:
    html: str
    sanitizer_version: str
    cache_key: str
    block_start_lines: tuple[int, ...] = ()


def validate_source_text(source: str) -> None:
    if not isinstance(source, str):
        raise RenderingError("Content source must be text")
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise RenderingError("Content source exceeds the configured limit")


def render_cache_key(
    source: str,
    *,
    version: str = SANITIZER_VERSION,
    content_format: str = "html",
    policy_fingerprint: str = "",
    allowed_media_ids: set[str] | frozenset[str] | tuple[str, ...] = (),
) -> str:
    validate_source_text(source)
    digest = sha256()
    for component in (
        version,
        content_format,
        policy_fingerprint,
        *sorted(str(item) for item in allowed_media_ids),
        source,
    ):
        encoded = component.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def sanitize_candidate_html(
    candidate_html: str,
    *,
    source: str,
    content_format: str,
    embed_policy: TrustedEmbedPolicy | None = None,
    allowed_media_ids: set[str] | frozenset[str] | tuple[str, ...] = (),
) -> RenderedContent:
    validate_source_text(source)
    if not isinstance(candidate_html, str):
        raise RenderingError("Rendered candidate must be text")
    if len(candidate_html.encode("utf-8")) > MAX_CANDIDATE_BYTES:
        raise RenderingError("Rendered candidate exceeds the safety limit")
    policy = embed_policy or configured_trusted_embed_policy()
    normalized_media_ids = _normalize_media_ids(allowed_media_ids)
    cleaned = nh3.clean(
        candidate_html,
        tags=_ALLOWED_TAGS,
        clean_content_tags=_CLEAN_CONTENT_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        strip_comments=True,
        link_rel=None,
        url_schemes={"http", "https", "mailto", "media"},
    )
    transformer = _SafeFragmentTransformer(policy, normalized_media_ids)
    transformer.feed(cleaned)
    transformer.close()
    return RenderedContent(
        html=transformer.html,
        sanitizer_version=SANITIZER_VERSION,
        cache_key=render_cache_key(
            source,
            content_format=content_format,
            policy_fingerprint=policy.fingerprint,
            allowed_media_ids=normalized_media_ids,
        ),
    )


def render_author_html(
    source: str,
    *,
    embed_policy: TrustedEmbedPolicy | None = None,
    allowed_media_ids: set[str] | frozenset[str] | tuple[str, ...] = (),
) -> RenderedContent:
    return sanitize_candidate_html(
        source,
        source=source,
        content_format="html",
        embed_policy=embed_policy,
        allowed_media_ids=allowed_media_ids,
    )


def configured_rendering_version() -> str:
    fingerprint = configured_trusted_embed_policy().fingerprint[:16]
    return f"{SANITIZER_VERSION}-p{fingerprint}"


def _normalize_media_ids(media_ids: object) -> frozenset[str]:
    if isinstance(media_ids, (str, bytes)):
        raise RenderingError("Allowed media IDs must be a collection")
    try:
        return frozenset(normalize_ulid(str(item)) for item in media_ids)  # type: ignore[union-attr]
    except (TypeError, ValueError) as exc:
        raise RenderingError("Allowed media IDs must contain valid ULIDs") from exc


class _SafeFragmentTransformer(HTMLParser):
    def __init__(
        self,
        embed_policy: TrustedEmbedPolicy,
        allowed_media_ids: frozenset[str],
    ) -> None:
        super().__init__(convert_charrefs=True)
        self._embed_policy = embed_policy
        self._allowed_media_ids = allowed_media_ids
        self._parts: list[str] = []
        self._embed_depth = 0

    @property
    def html(self) -> str:
        return "".join(self._parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._embed_depth:
            if tag == "kaj-embed":
                self._embed_depth += 1
            return
        values = {name: value or "" for name, value in attrs}
        if tag == "kaj-embed":
            rendered = self._embed_policy.render(
                values.get("data-source", ""), values.get("data-url", "")
            )
            self._parts.append(rendered or '<span role="note">来源不可用</span>')
            self._embed_depth = 1
            return
        if tag == "a":
            self._append_link(values)
            return
        if tag == "img":
            self._append_image(values)
            return
        safe_attrs: list[tuple[str, str]] = []
        if tag == "ol" and values.get("start", "").isdigit():
            safe_attrs.append(("start", values["start"]))
        self._append_start(tag, safe_attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._embed_depth:
            if tag == "kaj-embed":
                self._embed_depth -= 1
            return
        if tag not in _VOID_TAGS and tag != "kaj-embed":
            self._parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._embed_depth:
            self._parts.append(escape(data, quote=False))

    def _append_link(self, attrs: dict[str, str]) -> None:
        href = _safe_link(attrs.get("href", ""))
        safe_attrs: list[tuple[str, str]] = []
        if href is not None:
            normalized_href, external = href
            safe_attrs.append(("href", normalized_href))
            if attrs.get("title"):
                safe_attrs.append(("title", attrs["title"]))
            if external:
                safe_attrs.extend(
                    (("rel", "noopener noreferrer"), ("target", "_blank"))
                )
        self._append_start("a", safe_attrs)

    def _append_image(self, attrs: dict[str, str]) -> None:
        source = attrs.get("src", "")
        if not source.startswith("media:"):
            return
        try:
            media_id = normalize_ulid(source.removeprefix("media:"))
        except (TypeError, ValueError):
            return
        if media_id not in self._allowed_media_ids:
            return
        safe_attrs = [("src", f"/_kaj/media/{media_id}")]
        for name in ("alt", "title"):
            if attrs.get(name):
                safe_attrs.append((name, attrs[name]))
        self._append_start("img", safe_attrs)

    def _append_start(self, tag: str, attrs: list[tuple[str, str]]) -> None:
        serialized = "".join(
            f' {name}="{escape(value, quote=True)}"' for name, value in attrs
        )
        self._parts.append(f"<{tag}{serialized}>")


def _safe_link(value: str) -> tuple[str, bool] | None:
    if not value or value != value.strip() or any(ord(char) < 32 for char in value):
        return None
    if value.startswith(("//", "\\")):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if not parsed.scheme:
        if parsed.netloc:
            return None
        return value, False
    if parsed.scheme == "mailto":
        if parsed.netloc or not parsed.path:
            return None
        return value, False
    if parsed.scheme not in {"http", "https"}:
        return None
    if (
        parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
    ):
        return None
    return value, True
