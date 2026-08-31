from __future__ import annotations

from dataclasses import dataclass, replace
from html import escape
from typing import Any, Literal

from .embeds import (
    TrustedEmbedPolicy,
    configured_trusted_embed_policy,
)
from .headings import heading_text, legacy_heading_anchor
from .html_policy import (
    RenderedContent,
    RenderingError,
    normalize_allowed_media_ids,
    sanitize_candidate_html,
)
from .latex import render_latex_block
from .tiptap_schema import (
    LEGACY_TIPTAP_SCHEMA_VERSION,
    TIPTAP_CODE_LANGUAGES,
    NormalizedTipTapDocument,
    TipTapSchemaError,
    normalize_tiptap_document,
)

_MARK_TAGS = {
    "bold": "strong",
    "code": "code",
    "italic": "em",
    "strike": "s",
    "underline": "u",
}
_MARK_PRIORITY = {
    "code": 0,
    "bold": 1,
    "italic": 2,
    "strike": 3,
    "underline": 4,
    "link": 5,
}
UnavailableResourceBehavior = Literal["reject", "placeholder", "omit"]
TIPTAP_RENDERER_VERSION = "kaj-tiptap-renderer-v7"

_ATTACHMENT_TYPE_LABELS = {
    "application/zip": "ZIP",
    "application/x-7z-compressed": "7z",
    "application/vnd.rar": "RAR",
    "text/markdown": "Markdown",
    "text/plain": "TXT",
}


@dataclass(frozen=True, slots=True)
class TipTapAttachmentMetadata:
    asset_id: str
    original_name: str
    detected_mime: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class TipTapOutlineItem:
    anchor: str
    level: int
    text: str


def _project_normalized_outline(
    document: dict[str, Any],
) -> tuple[TipTapOutlineItem, ...]:
    items: list[TipTapOutlineItem] = []

    def visit(node: dict[str, Any]) -> None:
        if node["type"] == "heading":
            anchor = node["attrs"].get("anchor") or legacy_heading_anchor(
                node, len(items)
            )
            items.append(
                TipTapOutlineItem(
                    anchor=anchor,
                    level=node["attrs"]["level"],
                    text=heading_text(node),
                )
            )
        for child in node.get("content", ()):
            visit(child)

    visit(document)
    return tuple(items)


def project_tiptap_outline(
    document: dict[str, Any], *, schema_version: int = LEGACY_TIPTAP_SCHEMA_VERSION
) -> tuple[TipTapOutlineItem, ...]:
    normalized = normalize_tiptap_document(document, schema_version=schema_version)
    return _project_normalized_outline(normalized.document)


def render_tiptap(
    document: dict[str, Any] | NormalizedTipTapDocument,
    *,
    schema_version: int = LEGACY_TIPTAP_SCHEMA_VERSION,
    embed_policy: TrustedEmbedPolicy | None = None,
    allowed_media_ids: set[str] | frozenset[str] | tuple[str, ...] = (),
    allowed_attachment_id: str | None = None,
    attachment_metadata: TipTapAttachmentMetadata | None = None,
    unavailable_resources: UnavailableResourceBehavior = "reject",
) -> RenderedContent:
    if isinstance(document, NormalizedTipTapDocument):
        if document.schema_version != schema_version:
            raise TipTapSchemaError(
                "media.tiptap.version_invalid.v1",
                "Normalized TipTap schema version does not match",
            )
        normalized = document
    else:
        normalized = normalize_tiptap_document(
            document,
            schema_version=schema_version,
        )
    if unavailable_resources not in {"omit", "placeholder", "reject"}:
        raise RenderingError("Unavailable-resource behavior is invalid")
    normalized_media_ids = normalize_allowed_media_ids(allowed_media_ids)
    normalized_attachment_id = _normalize_attachment_id(allowed_attachment_id)
    normalized_attachment_metadata = _normalize_attachment_metadata(
        attachment_metadata,
        normalized_attachment_id,
    )
    policy = embed_policy or configured_trusted_embed_policy()
    renderer = _TipTapRenderer(
        embed_policy=policy,
        allowed_media_ids=normalized_media_ids,
        allowed_attachment_id=normalized_attachment_id,
        attachment_metadata=normalized_attachment_metadata,
        unavailable_resources=unavailable_resources,
        heading_anchors=tuple(
            item.anchor for item in _project_normalized_outline(normalized.document)
        ),
    )
    candidate = renderer.render(normalized.document)
    rendered = sanitize_candidate_html(
        candidate,
        source=normalized.serialized,
        content_format=(
            f"tiptap-v{normalized.schema_version}-{TIPTAP_RENDERER_VERSION}"
        ),
        embed_policy=policy,
        allowed_media_ids=normalized_media_ids,
    )
    return replace(
        rendered,
        node_count=normalized.node_count,
        max_depth=normalized.max_depth,
        table_cells=normalized.table_cells,
    )


def _normalize_attachment_id(value: str | None) -> str | None:
    if value is None:
        return None
    return next(iter(normalize_allowed_media_ids((value,))))


def _normalize_attachment_metadata(
    value: TipTapAttachmentMetadata | None,
    allowed_attachment_id: str | None,
) -> TipTapAttachmentMetadata | None:
    if value is None:
        return None
    if not isinstance(value, TipTapAttachmentMetadata):
        raise RenderingError("Attachment metadata is invalid")
    asset_id = _normalize_attachment_id(value.asset_id)
    if asset_id != allowed_attachment_id:
        raise RenderingError("Attachment metadata does not match the allowed asset")
    if (
        not isinstance(value.original_name, str)
        or not value.original_name
        or len(value.original_name) > 255
        or any(ord(character) < 32 for character in value.original_name)
        or "/" in value.original_name
        or "\\" in value.original_name
        or value.detected_mime not in _ATTACHMENT_TYPE_LABELS
        or type(value.size_bytes) is not int
        or value.size_bytes < 0
    ):
        raise RenderingError("Attachment metadata is invalid")
    return TipTapAttachmentMetadata(
        asset_id=asset_id,
        original_name=value.original_name,
        detected_mime=value.detected_mime,
        size_bytes=value.size_bytes,
    )


def _attachment_size(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KiB"
    return f"{value / 1024 / 1024:.1f} MiB"


class _TipTapRenderer:
    def __init__(
        self,
        *,
        embed_policy: TrustedEmbedPolicy,
        allowed_media_ids: frozenset[str],
        allowed_attachment_id: str | None,
        attachment_metadata: TipTapAttachmentMetadata | None,
        unavailable_resources: UnavailableResourceBehavior,
        heading_anchors: tuple[str, ...],
    ) -> None:
        self._embed_policy = embed_policy
        self._allowed_media_ids = allowed_media_ids
        self._allowed_attachment_id = allowed_attachment_id
        self._attachment_metadata = attachment_metadata
        self._unavailable_resources = unavailable_resources
        self._heading_anchors = iter(heading_anchors)

    def render(self, document: dict[str, Any]) -> str:
        return self._render_node(document)

    def _render_node(self, node: dict[str, Any]) -> str:
        node_type = node["type"]
        if node_type == "doc":
            return self._render_children(node)
        if node_type == "text":
            return self._render_text(node)
        if node_type == "hardBreak":
            return "<br>"
        if node_type == "horizontalRule":
            return "<hr>"
        if node_type == "image":
            return self._render_image(node)
        if node_type == "heading":
            level = node["attrs"]["level"]
            anchor = next(self._heading_anchors)
            return f'<h{level} id="{anchor}">{self._render_children(node)}</h{level}>'
        if node_type in {"paragraph", "blockquote", "bulletList", "listItem"}:
            return self._render_container(node, node_type)
        if node_type == "orderedList":
            return self._render_ordered_list(node)
        if node_type == "codeBlock":
            return self._render_code_block(node)
        if node_type == "taskList":
            return f'<ul data-task-list="true">{self._render_children(node)}</ul>'
        if node_type == "taskItem":
            return self._render_task_item(node)
        if node_type == "callout":
            kind = node["attrs"]["kind"]
            return f'<aside data-callout="{kind}">{self._render_children(node)}</aside>'
        if node_type == "table":
            return self._render_table(node)
        if node_type == "tableRow":
            return f"<tr>{self._render_children(node)}</tr>"
        if node_type in {"tableHeader", "tableCell"}:
            tag = "th" if node_type == "tableHeader" else "td"
            return f"<{tag}>{self._render_children(node)}</{tag}>"
        if node_type == "attachment":
            return self._render_attachment(node)
        if node_type == "embed":
            return self._render_embed(node)
        if node_type == "latexBlock":
            return render_latex_block(node["attrs"]["formula"])
        raise TipTapSchemaError(
            "media.tiptap.node_unsupported.v1", "TipTap node is unsupported"
        )

    def _render_children(self, node: dict[str, Any]) -> str:
        return "".join(self._render_node(child) for child in node.get("content", ()))

    def _render_text(self, node: dict[str, Any]) -> str:
        rendered = escape(node["text"], quote=False)
        marks = sorted(
            node.get("marks", ()), key=lambda item: _MARK_PRIORITY[item["type"]]
        )
        for mark in marks:
            mark_type = mark["type"]
            if mark_type == "link":
                rendered = self._wrap_link(rendered, mark)
                continue
            tag = _MARK_TAGS[mark_type]
            rendered = f"<{tag}>{rendered}</{tag}>"
        return rendered

    def _wrap_link(self, rendered: str, mark: dict[str, Any]) -> str:
        attrs = mark["attrs"]
        href = attrs["href"]
        title = attrs.get("title")
        serialized = f' href="{escape(href, quote=True)}"'
        if title:
            serialized += f' title="{escape(title, quote=True)}"'
        return f"<a{serialized}>{rendered}</a>"

    def _render_image(self, node: dict[str, Any]) -> str:
        attrs = node["attrs"]
        media_id = attrs["src"].removeprefix("media:")
        if media_id not in self._allowed_media_ids:
            return self._unavailable("&#22270;&#29255;&#19981;&#21487;&#29992;")
        values = [f'src="{escape(attrs["src"], quote=True)}"']
        for name in ("alt", "title"):
            value = attrs.get(name)
            if value:
                values.append(f'{name}="{escape(value, quote=True)}"')
        if "width" in attrs:
            values.append(f'data-width="{attrs["width"]}"')
        return f"<img {' '.join(values)}>"

    def _render_container(self, node: dict[str, Any], node_type: str) -> str:
        tag = {
            "paragraph": "p",
            "blockquote": "blockquote",
            "bulletList": "ul",
            "listItem": "li",
        }[node_type]
        return f"<{tag}>{self._render_children(node)}</{tag}>"

    def _render_ordered_list(self, node: dict[str, Any]) -> str:
        attrs = node.get("attrs", {})
        start = attrs.get("start", 1)
        serialized = f' start="{start}"' if start != 1 else ""
        return f"<ol{serialized}>{self._render_children(node)}</ol>"

    def _render_code_block(self, node: dict[str, Any]) -> str:
        language = node.get("attrs", {}).get("language", "text")
        attribute = (
            f' data-language="{language}"' if language in TIPTAP_CODE_LANGUAGES else ""
        )
        return f"<pre><code{attribute}>{self._render_children(node)}</code></pre>"

    def _render_task_item(self, node: dict[str, Any]) -> str:
        checked = node["attrs"]["checked"]
        checked_value = "true" if checked else "false"
        checked_attribute = " checked" if checked else ""
        checkbox = f'<input type="checkbox" disabled{checked_attribute}>'
        return (
            f'<li data-task-checked="{checked_value}">'
            f"{checkbox}{self._render_children(node)}</li>"
        )

    def _render_table(self, node: dict[str, Any]) -> str:
        rows = node["content"]
        if rows[0]["content"][0]["type"] == "tableHeader":
            head = self._render_node(rows[0])
            body = "".join(self._render_node(row) for row in rows[1:])
            table = f"<table><thead>{head}</thead><tbody>{body}</tbody></table>"
        else:
            table = f"<table><tbody>{self._render_children(node)}</tbody></table>"
        return f'<div data-table-scroll="true">{table}</div>'

    def _render_attachment(self, node: dict[str, Any]) -> str:
        media_id = node["attrs"]["src"].removeprefix("media:")
        if media_id != self._allowed_attachment_id:
            return self._unavailable("&#38468;&#20214;&#19981;&#21487;&#29992;")
        metadata = self._attachment_metadata
        name = (
            metadata.original_name if metadata else "&#25991;&#31456;&#38468;&#20214;"
        )
        detail = (
            f"{_ATTACHMENT_TYPE_LABELS[metadata.detected_mime]}"
            f" &#183; {_attachment_size(metadata.size_bytes)}"
            if metadata
            else "&#21487;&#19979;&#36733;&#25991;&#20214;"
        )
        download = (
            f' download="{escape(metadata.original_name, quote=True)}"'
            if metadata
            else " download"
        )
        return (
            '<aside data-kaj-attachment-card="true">'
            f"<strong>{escape(name, quote=False) if metadata else name}</strong>"
            f"<span>{detail}</span>"
            f'<a href="/_kaj/media/{media_id}" data-kaj-attachment="true"{download}>'
            "&#19979;&#36733;</a></aside>"
        )

    def _render_embed(self, node: dict[str, Any]) -> str:
        attrs = node["attrs"]
        if self._embed_policy.render(attrs["source"], attrs["url"]) is None:
            if self._unavailable_resources == "reject":
                raise TipTapSchemaError(
                    "media.tiptap.embed_invalid.v1",
                    "TipTap embed source is unavailable",
                )
            if self._unavailable_resources == "omit":
                return ""
        source = escape(attrs["source"], quote=True)
        url = escape(attrs["url"], quote=True)
        return f'<kaj-embed data-source="{source}" data-url="{url}"></kaj-embed>'

    def _unavailable(self, label: str) -> str:
        if self._unavailable_resources == "reject":
            raise TipTapSchemaError(
                "media.tiptap.media_invalid.v1",
                "TipTap media is unavailable",
            )
        if self._unavailable_resources == "omit":
            return ""
        return f'<span role="note">{label}</span>'
