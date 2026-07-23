from __future__ import annotations

import json
from html import escape
from typing import Any

from .embeds import TrustedEmbedPolicy
from .html_policy import (
    MAX_SOURCE_BYTES,
    RenderedContent,
    RenderingError,
    sanitize_candidate_html,
)

MAX_NODES = 10_000
MAX_DEPTH = 100

_BLOCK_NODES = {
    "blockquote",
    "bulletList",
    "codeBlock",
    "heading",
    "horizontalRule",
    "image",
    "orderedList",
    "paragraph",
}
_INLINE_NODES = {"hardBreak", "image", "text"}
_MARK_TAGS = {
    "bold": "strong",
    "code": "code",
    "italic": "em",
    "strike": "s",
    "underline": "u",
}


def render_tiptap(
    document: dict[str, Any],
    *,
    embed_policy: TrustedEmbedPolicy | None = None,
    allowed_media_ids: set[str] | frozenset[str] | tuple[str, ...] = (),
) -> RenderedContent:
    try:
        source = json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise RenderingError("TipTap document must be JSON serializable") from exc
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise RenderingError("Content source exceeds the configured limit")
    renderer = _TipTapRenderer()
    candidate = renderer.render(document)
    return sanitize_candidate_html(
        candidate,
        source=source,
        content_format="tiptap",
        embed_policy=embed_policy,
        allowed_media_ids=allowed_media_ids,
    )


class _TipTapRenderer:
    def __init__(self) -> None:
        self._node_count = 0

    def render(self, document: object) -> str:
        if not isinstance(document, dict):
            raise RenderingError("TipTap document root must be an object")
        return self._render_node(document, 0, {"doc"})

    def _render_node(
        self, node: dict[str, Any], depth: int, allowed_types: set[str]
    ) -> str:
        self._node_count += 1
        if self._node_count > MAX_NODES or depth > MAX_DEPTH:
            raise RenderingError("TipTap document exceeds structural limits")
        if not isinstance(node, dict) or not isinstance(node.get("type"), str):
            raise RenderingError("Every TipTap node must have a string type")
        node_type = node["type"]
        if node_type not in allowed_types:
            raise RenderingError(f"Unsupported TipTap node: {node_type}")
        if node_type == "doc":
            self._require_keys(node, {"type", "content"})
            return self._render_children(node, depth, _BLOCK_NODES)
        if node_type == "text":
            return self._render_text(node)
        if node_type == "hardBreak":
            self._require_keys(node, {"type"})
            return "<br>"
        if node_type == "horizontalRule":
            self._require_keys(node, {"type"})
            return "<hr>"
        if node_type == "image":
            return self._render_image(node)
        if node_type == "heading":
            return self._render_heading(node, depth)
        if node_type in {"paragraph", "blockquote", "bulletList", "listItem"}:
            return self._render_container(node, depth, node_type)
        if node_type == "orderedList":
            return self._render_ordered_list(node, depth)
        if node_type == "codeBlock":
            return self._render_code_block(node, depth)
        raise RenderingError(f"Unsupported TipTap node: {node_type}")

    def _render_children(
        self, node: dict[str, Any], depth: int, allowed_types: set[str]
    ) -> str:
        children = node.get("content", [])
        if not isinstance(children, list):
            raise RenderingError("TipTap node content must be a list")
        rendered: list[str] = []
        for child in children:
            if not isinstance(child, dict):
                raise RenderingError("TipTap child nodes must be objects")
            rendered.append(self._render_node(child, depth + 1, allowed_types))
        return "".join(rendered)

    def _render_text(self, node: dict[str, Any]) -> str:
        self._require_keys(node, {"type", "text", "marks"})
        text = node.get("text")
        if not isinstance(text, str):
            raise RenderingError("TipTap text nodes require text")
        rendered = escape(text, quote=False)
        marks = node.get("marks", [])
        if not isinstance(marks, list):
            raise RenderingError("TipTap marks must be a list")
        seen: set[str] = set()
        for mark in marks:
            if not isinstance(mark, dict) or not isinstance(mark.get("type"), str):
                raise RenderingError("TipTap marks must be typed objects")
            mark_type = mark["type"]
            if mark_type in seen:
                raise RenderingError("TipTap marks cannot be duplicated")
            seen.add(mark_type)
            if mark_type == "link":
                rendered = self._wrap_link(rendered, mark)
                continue
            tag = _MARK_TAGS.get(mark_type)
            if tag is None:
                raise RenderingError(f"Unsupported TipTap mark: {mark_type}")
            self._require_keys(mark, {"type"})
            rendered = f"<{tag}>{rendered}</{tag}>"
        return rendered

    def _wrap_link(self, rendered: str, mark: dict[str, Any]) -> str:
        self._require_keys(mark, {"type", "attrs"})
        attrs = mark.get("attrs")
        if not isinstance(attrs, dict):
            raise RenderingError("TipTap link marks require attributes")
        self._require_keys(attrs, {"href", "title"}, required={"href"})
        href = attrs.get("href")
        title = attrs.get("title")
        if not isinstance(href, str) or (
            title is not None and not isinstance(title, str)
        ):
            raise RenderingError("TipTap link attributes must be text")
        serialized = f' href="{escape(href, quote=True)}"'
        if title:
            serialized += f' title="{escape(title, quote=True)}"'
        return f"<a{serialized}>{rendered}</a>"

    def _render_image(self, node: dict[str, Any]) -> str:
        self._require_keys(node, {"type", "attrs"})
        attrs = node.get("attrs")
        if not isinstance(attrs, dict):
            raise RenderingError("TipTap images require attributes")
        self._require_keys(attrs, {"src", "alt", "title"}, required={"src"})
        if not isinstance(attrs.get("src"), str):
            raise RenderingError("TipTap image sources must be text")
        values = [f'src="{escape(attrs["src"], quote=True)}"']
        for name in ("alt", "title"):
            value = attrs.get(name)
            if value is not None and not isinstance(value, str):
                raise RenderingError("TipTap image attributes must be text")
            if value:
                values.append(f'{name}="{escape(value, quote=True)}"')
        return f"<img {' '.join(values)}>"

    def _render_heading(self, node: dict[str, Any], depth: int) -> str:
        self._require_keys(node, {"type", "attrs", "content"})
        attrs = node.get("attrs")
        if not isinstance(attrs, dict):
            raise RenderingError("TipTap headings require attributes")
        self._require_keys(attrs, {"level"}, required={"level"})
        level = attrs.get("level")
        if type(level) is not int or not 1 <= level <= 6:
            raise RenderingError("TipTap heading level must be between 1 and 6")
        content = self._render_children(node, depth, _INLINE_NODES)
        return f"<h{level}>{content}</h{level}>"

    def _render_container(
        self, node: dict[str, Any], depth: int, node_type: str
    ) -> str:
        self._require_keys(node, {"type", "content"})
        tag, allowed = {
            "paragraph": ("p", _INLINE_NODES),
            "blockquote": ("blockquote", _BLOCK_NODES),
            "bulletList": ("ul", {"listItem"}),
            "listItem": ("li", _BLOCK_NODES),
        }[node_type]
        content = self._render_children(node, depth, allowed)
        return f"<{tag}>{content}</{tag}>"

    def _render_ordered_list(self, node: dict[str, Any], depth: int) -> str:
        self._require_keys(node, {"type", "attrs", "content"})
        attrs = node.get("attrs", {})
        if not isinstance(attrs, dict):
            raise RenderingError("TipTap ordered-list attributes must be an object")
        self._require_keys(attrs, {"start"})
        start = attrs.get("start", 1)
        if type(start) is not int or start < 1:
            raise RenderingError("TipTap ordered-list start must be positive")
        serialized = f' start="{start}"' if start != 1 else ""
        content = self._render_children(node, depth, {"listItem"})
        return f"<ol{serialized}>{content}</ol>"

    def _render_code_block(self, node: dict[str, Any], depth: int) -> str:
        self._require_keys(node, {"type", "attrs", "content"})
        attrs = node.get("attrs", {})
        if not isinstance(attrs, dict):
            raise RenderingError("TipTap code-block attributes must be an object")
        self._require_keys(attrs, {"language"})
        language = attrs.get("language")
        if language is not None and not isinstance(language, str):
            raise RenderingError("TipTap code-block language must be text")
        content = self._render_children(node, depth, {"text"})
        return f"<pre><code>{content}</code></pre>"

    @staticmethod
    def _require_keys(
        value: dict[str, Any], allowed: set[str], *, required: set[str] | None = None
    ) -> None:
        if not set(value).issubset(allowed) or not (required or set()).issubset(value):
            raise RenderingError("TipTap document contains unexpected fields")
