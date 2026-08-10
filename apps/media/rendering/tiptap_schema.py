from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from apps.core.ids import normalize_ulid

from .headings import is_safe_heading_anchor
from .html_policy import MAX_SOURCE_BYTES, RenderingError, normalize_safe_link

LEGACY_TIPTAP_SCHEMA_VERSION = 1
CURRENT_TIPTAP_SCHEMA_VERSION = 2
SUPPORTED_TIPTAP_SCHEMA_VERSIONS = frozenset(
    {LEGACY_TIPTAP_SCHEMA_VERSION, CURRENT_TIPTAP_SCHEMA_VERSION}
)
TIPTAP_SCHEMA_FINGERPRINT = "kaj-tiptap-v1-v2-heading-anchor"
MAX_TIPTAP_NODES = 10_000
MAX_TIPTAP_DEPTH = 100
MAX_TIPTAP_TABLE_ROWS = 50
MAX_TIPTAP_TABLE_COLUMNS = 20
MAX_TIPTAP_TABLE_CELLS = 1_000

_V1_BLOCKS = frozenset(
    {
        "blockquote",
        "bulletList",
        "codeBlock",
        "heading",
        "horizontalRule",
        "image",
        "orderedList",
        "paragraph",
    }
)
_V2_BLOCKS = _V1_BLOCKS | {
    "attachment",
    "callout",
    "embed",
    "table",
    "taskList",
}
_INLINE_NODES = frozenset({"hardBreak", "image", "text"})
_MARKS = frozenset({"bold", "code", "italic", "link", "strike", "underline"})
TIPTAP_CODE_LANGUAGES = frozenset(
    {
        "bash",
        "css",
        "diff",
        "html",
        "javascript",
        "json",
        "markdown",
        "python",
        "sql",
        "text",
        "typescript",
        "yaml",
    }
)
_IMAGE_WIDTHS = frozenset({25, 50, 75, 100})
_CALLOUT_KINDS = frozenset({"info", "success", "warning"})


class TipTapSchemaError(RenderingError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class NormalizedTipTapDocument:
    document: dict[str, Any]
    serialized: str
    schema_version: int
    body_media_ids: tuple[str, ...]
    attachment_media_ids: tuple[str, ...]
    node_count: int
    max_depth: int
    table_cells: int


def normalize_tiptap_document(
    document: dict[str, Any], *, schema_version: int
) -> NormalizedTipTapDocument:
    version = _schema_version(schema_version)
    validator = _TipTapSchemaValidator(version)
    normalized = validator.validate(document)
    try:
        serialized = json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise TipTapSchemaError(
            "media.tiptap.root_invalid.v1", "TipTap document must be JSON serializable"
        ) from exc
    if len(serialized.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise TipTapSchemaError(
            "media.tiptap.source_limit.v1", "TipTap source exceeds the configured limit"
        )
    return NormalizedTipTapDocument(
        document=normalized,
        serialized=serialized,
        schema_version=version,
        body_media_ids=tuple(dict.fromkeys(validator.body_media_ids)),
        attachment_media_ids=tuple(dict.fromkeys(validator.attachment_media_ids)),
        node_count=validator.node_count,
        max_depth=validator.max_depth,
        table_cells=validator.table_cells,
    )


def _schema_version(value: object) -> int:
    if type(value) is not int or value not in SUPPORTED_TIPTAP_SCHEMA_VERSIONS:
        raise TipTapSchemaError(
            "media.tiptap.version_invalid.v1", "Unsupported TipTap schema version"
        )
    return value


class _TipTapSchemaValidator:
    def __init__(self, version: int) -> None:
        self.version = version
        self.node_count = 0
        self.max_depth = 0
        self.table_cells = 0
        self.table_depth = 0
        self.attachment_count = 0
        self.heading_anchors: set[str] = set()
        self.blocks = _V1_BLOCKS if version == 1 else _V2_BLOCKS
        self.body_media_ids: list[str] = []
        self.attachment_media_ids: list[str] = []

    def validate(self, document: object) -> dict[str, Any]:
        if not isinstance(document, dict):
            self._fail("root_invalid", "TipTap document root must be an object")
        return self._node(document, depth=0, allowed={"doc"}, parent="root")

    def _node(
        self,
        node: object,
        *,
        depth: int,
        allowed: set[str] | frozenset[str],
        parent: str,
    ) -> dict[str, Any]:
        self.node_count += 1
        self.max_depth = max(self.max_depth, depth)
        if self.node_count > MAX_TIPTAP_NODES or depth > MAX_TIPTAP_DEPTH:
            self._fail("structure_limit", "TipTap document exceeds structural limits")
        if not isinstance(node, dict) or not isinstance(node.get("type"), str):
            self._fail("node_invalid", "Every TipTap node must have a string type")
        node_type = node["type"]
        if node_type not in allowed:
            self._fail("node_unsupported", "TipTap node is unsupported")

        if node_type == "text":
            return self._text(node, parent=parent)
        if node_type in {"hardBreak", "horizontalRule"}:
            self._keys(node, {"type"})
            return {"type": node_type}
        if node_type == "image":
            return self._image(node)
        if node_type == "heading":
            return self._heading(node, depth)
        if node_type in {"paragraph", "blockquote", "listItem", "callout"}:
            return self._container(node, depth, node_type)
        if node_type in {"bulletList", "orderedList", "taskList"}:
            return self._list(node, depth, node_type)
        if node_type == "taskItem":
            return self._task_item(node, depth)
        if node_type == "codeBlock":
            return self._code_block(node, depth)
        if node_type == "table":
            return self._table(node, depth)
        if node_type == "tableRow":
            return self._table_row(node, depth)
        if node_type in {"tableHeader", "tableCell"}:
            return self._table_cell(node, depth, node_type)
        if node_type == "attachment":
            return self._attachment(node)
        if node_type == "embed":
            return self._embed(node)
        if node_type == "doc":
            self._keys(node, {"type", "content"})
            return {"type": "doc", "content": self._children(node, depth, self.blocks)}
        self._fail("node_unsupported", "TipTap node is unsupported")

    def _text(self, node: dict[str, Any], *, parent: str) -> dict[str, Any]:
        self._keys(node, {"type", "text", "marks"}, required={"text"})
        text = node.get("text")
        if not isinstance(text, str):
            self._fail("text_invalid", "TipTap text nodes require text")
        self._require_utf8(text, code="text_invalid", message="TipTap text is invalid")
        marks = node.get("marks", [])
        if parent == "codeBlock" and marks:
            self._fail("mark_invalid", "Code block text cannot have marks")
        normalized_marks = self._marks(marks)
        result: dict[str, Any] = {"type": "text", "text": text}
        if normalized_marks:
            result["marks"] = normalized_marks
        return result

    def _marks(self, marks: object) -> list[dict[str, Any]]:
        if not isinstance(marks, list):
            self._fail("mark_invalid", "TipTap marks must be a list")
        result = []
        seen = set()
        for mark in marks:
            if not isinstance(mark, dict) or not isinstance(mark.get("type"), str):
                self._fail("mark_invalid", "TipTap marks must be typed objects")
            mark_type = mark["type"]
            if mark_type not in _MARKS or mark_type in seen:
                self._fail("mark_invalid", "TipTap mark is unsupported or duplicated")
            seen.add(mark_type)
            if mark_type != "link":
                self._keys(mark, {"type"}, code="mark_invalid")
                result.append({"type": mark_type})
                continue
            self._keys(mark, {"type", "attrs"}, required={"attrs"}, code="mark_invalid")
            attrs = mark.get("attrs")
            if not isinstance(attrs, dict):
                self._fail("mark_invalid", "TipTap link marks require attributes")
            self._keys(attrs, {"href", "title"}, required={"href"}, code="mark_invalid")
            href, title = attrs.get("href"), attrs.get("title")
            if not isinstance(href, str) or not href:
                self._fail("link_invalid", "TipTap link requires a URL")
            self._require_utf8(
                href,
                code="link_invalid",
                message="TipTap link URL is invalid",
            )
            safe_link = normalize_safe_link(href)
            if safe_link is None and self.version != LEGACY_TIPTAP_SCHEMA_VERSION:
                self._fail("link_invalid", "TipTap link URL is unsafe")
            if title is not None and not isinstance(title, str):
                self._fail("mark_invalid", "TipTap link title must be text")
            if title is not None:
                self._require_utf8(
                    title,
                    code="mark_invalid",
                    message="TipTap link title is invalid",
                )
            normalized_attrs = {"href": safe_link[0] if safe_link else href}
            if title:
                normalized_attrs["title"] = title
            result.append({"type": "link", "attrs": normalized_attrs})
        return result

    def _image(self, node: dict[str, Any]) -> dict[str, Any]:
        self._keys(node, {"type", "attrs"}, required={"attrs"})
        attrs = node.get("attrs")
        if not isinstance(attrs, dict):
            self._fail(
                "attributes_invalid", "TipTap image attributes must be an object"
            )
        allowed = {"src", "alt", "title"} | ({"width"} if self.version == 2 else set())
        self._keys(attrs, allowed, required={"src"})
        source = self._media_source(attrs.get("src"))
        self.body_media_ids.append(source.removeprefix("media:"))
        result = {"src": source}
        for name in ("alt", "title"):
            value = attrs.get(name)
            if value is not None and not isinstance(value, str):
                self._fail(
                    "attributes_invalid", "TipTap image text attributes are invalid"
                )
            if value is not None:
                self._require_utf8(
                    value,
                    code="attributes_invalid",
                    message="TipTap image text attributes are invalid",
                )
            if value:
                result[name] = value
        if self.version == 2:
            width = attrs.get("width", 100)
            if type(width) is not int or width not in _IMAGE_WIDTHS:
                self._fail("attributes_invalid", "TipTap image width is invalid")
            if width != 100:
                result["width"] = width
        return {"type": "image", "attrs": result}

    def _heading(self, node: dict[str, Any], depth: int) -> dict[str, Any]:
        self._keys(node, {"type", "attrs", "content"}, required={"attrs"})
        attrs = node.get("attrs")
        if not isinstance(attrs, dict):
            self._fail("attributes_invalid", "TipTap heading attributes are invalid")
        allowed = {"level", "anchor"} if self.version == 2 else {"level"}
        self._keys(attrs, allowed, required={"level"})
        level = attrs.get("level")
        if type(level) is not int or not 1 <= level <= 6:
            self._fail("attributes_invalid", "TipTap heading level is invalid")
        normalized_attrs: dict[str, Any] = {"level": level}
        anchor = attrs.get("anchor")
        if anchor is not None:
            if not is_safe_heading_anchor(anchor, allow_legacy=False):
                self._fail("attributes_invalid", "TipTap heading anchor is invalid")
            if anchor in self.heading_anchors:
                self._fail("attributes_invalid", "TipTap heading anchor is duplicated")
            self.heading_anchors.add(anchor)
            normalized_attrs["anchor"] = anchor
        return {
            "type": "heading",
            "attrs": normalized_attrs,
            "content": self._children(node, depth, _INLINE_NODES),
        }

    def _container(
        self, node: dict[str, Any], depth: int, node_type: str
    ) -> dict[str, Any]:
        allowed_keys = (
            {"type", "attrs", "content"}
            if node_type == "callout"
            else {"type", "content"}
        )
        self._keys(node, allowed_keys)
        if node_type == "paragraph":
            allowed = _INLINE_NODES
            attrs = None
        elif node_type == "callout":
            allowed = self.blocks
            attrs = node.get("attrs")
            if not isinstance(attrs, dict):
                self._fail(
                    "attributes_invalid", "TipTap callout attributes are invalid"
                )
            self._keys(attrs, {"kind"}, required={"kind"})
            if attrs.get("kind") not in _CALLOUT_KINDS:
                self._fail("attributes_invalid", "TipTap callout kind is invalid")
        else:
            allowed = self.blocks
            attrs = None
        result = {"type": node_type, "content": self._children(node, depth, allowed)}
        if node_type == "callout":
            result["attrs"] = {"kind": attrs["kind"]}
        return result

    def _list(self, node: dict[str, Any], depth: int, node_type: str) -> dict[str, Any]:
        self._keys(node, {"type", "attrs", "content"})
        allowed = {"taskItem"} if node_type == "taskList" else {"listItem"}
        children = self._children(node, depth, allowed)
        if self.version == 2 and not children:
            self._fail("node_invalid", "TipTap lists require at least one item")
        result = {"type": node_type, "content": children}
        if node_type == "orderedList":
            attrs = node.get("attrs", {})
            if not isinstance(attrs, dict):
                self._fail("attributes_invalid", "Ordered-list attributes are invalid")
            self._keys(attrs, {"start"})
            start = attrs.get("start", 1)
            if type(start) is not int or start < 1:
                self._fail("attributes_invalid", "Ordered-list start must be positive")
            if start != 1:
                result["attrs"] = {"start": start}
        return result

    def _task_item(self, node: dict[str, Any], depth: int) -> dict[str, Any]:
        self._keys(node, {"type", "attrs", "content"}, required={"attrs"})
        attrs = node.get("attrs")
        if not isinstance(attrs, dict):
            self._fail("attributes_invalid", "Task item attributes are invalid")
        self._keys(attrs, {"checked"}, required={"checked"})
        if type(attrs.get("checked")) is not bool:
            self._fail("attributes_invalid", "Task item checked state must be boolean")
        children = self._children(node, depth, self.blocks)
        if not children:
            self._fail("node_invalid", "Task items require block content")
        return {
            "type": "taskItem",
            "attrs": {"checked": attrs["checked"]},
            "content": children,
        }

    def _code_block(self, node: dict[str, Any], depth: int) -> dict[str, Any]:
        self._keys(node, {"type", "attrs", "content"})
        attrs = node.get("attrs", {})
        if not isinstance(attrs, dict):
            self._fail("attributes_invalid", "Code-block attributes are invalid")
        self._keys(attrs, {"language"})
        language = attrs.get("language") or "text"
        if not isinstance(language, str):
            self._fail("attributes_invalid", "Code-block language must be text")
        self._require_utf8(
            language,
            code="attributes_invalid",
            message="Code-block language is invalid",
        )
        if self.version == 2 and language not in TIPTAP_CODE_LANGUAGES:
            self._fail("attributes_invalid", "Code-block language is unsupported")
        result = {"type": "codeBlock", "content": self._children(node, depth, {"text"})}
        if self.version == 2 or language != "text":
            result["attrs"] = {"language": language}
        return result

    def _table(self, node: dict[str, Any], depth: int) -> dict[str, Any]:
        if self.table_depth:
            self._fail("table_invalid", "Nested TipTap tables are invalid")
        self._keys(node, {"type", "content"}, code="table_invalid")
        self.table_depth += 1
        try:
            rows = self._table_children(node, depth, {"tableRow"})
        finally:
            self.table_depth -= 1
        if len(rows) > MAX_TIPTAP_TABLE_ROWS:
            self._fail("table_invalid", "TipTap table row count is invalid")
        widths = [len(row["content"]) for row in rows]
        if widths[0] > MAX_TIPTAP_TABLE_COLUMNS or len(set(widths)) != 1:
            self._fail("table_invalid", "TipTap table columns are invalid")
        if len(rows) * widths[0] > MAX_TIPTAP_TABLE_CELLS:
            self._fail("table_invalid", "TipTap table exceeds the cell limit")
        self.table_cells += len(rows) * widths[0]
        first_types = {cell["type"] for cell in rows[0]["content"]}
        if first_types not in ({"tableHeader"}, {"tableCell"}):
            self._fail("table_invalid", "TipTap table header row is invalid")
        if any(
            cell["type"] != "tableCell" for row in rows[1:] for cell in row["content"]
        ):
            self._fail("table_invalid", "TipTap table body contains header cells")
        return {"type": "table", "content": rows}

    def _table_row(self, node: dict[str, Any], depth: int) -> dict[str, Any]:
        self._keys(node, {"type", "content"}, code="table_invalid")
        return {
            "type": "tableRow",
            "content": self._table_children(
                node,
                depth,
                {"tableCell", "tableHeader"},
            ),
        }

    def _table_cell(
        self, node: dict[str, Any], depth: int, node_type: str
    ) -> dict[str, Any]:
        self._keys(node, {"type", "content"}, code="table_invalid")
        children = self._table_children(node, depth, self.blocks)
        return {"type": node_type, "content": children}

    def _table_children(
        self,
        node: dict[str, Any],
        depth: int,
        allowed: set[str] | frozenset[str],
    ) -> list[dict[str, Any]]:
        children = node.get("content")
        if not isinstance(children, list) or not children:
            self._fail("table_invalid", "TipTap table content is invalid")
        if any(
            not isinstance(child, dict) or child.get("type") not in allowed
            for child in children
        ):
            self._fail("table_invalid", "TipTap table structure is invalid")
        return self._children(node, depth, allowed)

    def _attachment(self, node: dict[str, Any]) -> dict[str, Any]:
        self.attachment_count += 1
        if self.attachment_count > 1:
            self._fail(
                "attachment_invalid",
                "TipTap document may contain only one attachment",
            )
        self._keys(node, {"type", "attrs"}, required={"attrs"})
        attrs = node.get("attrs")
        if not isinstance(attrs, dict):
            self._fail("attributes_invalid", "Attachment attributes are invalid")
        self._keys(attrs, {"src"}, required={"src"})
        source = self._media_source(attrs.get("src"))
        self.attachment_media_ids.append(source.removeprefix("media:"))
        return {"type": "attachment", "attrs": {"src": source}}

    def _embed(self, node: dict[str, Any]) -> dict[str, Any]:
        self._keys(node, {"type", "attrs"}, required={"attrs"})
        attrs = node.get("attrs")
        if not isinstance(attrs, dict):
            self._fail("attributes_invalid", "Embed attributes are invalid")
        self._keys(attrs, {"source", "url"}, required={"source", "url"})
        source, url = attrs.get("source"), attrs.get("url")
        if (
            not isinstance(source, str)
            or not source
            or not isinstance(url, str)
            or not url
        ):
            self._fail("embed_invalid", "Embed source and URL are required")
        self._require_utf8(
            source,
            code="embed_invalid",
            message="Embed source is invalid",
        )
        self._require_utf8(
            url,
            code="embed_invalid",
            message="Embed URL is invalid",
        )
        return {"type": "embed", "attrs": {"source": source, "url": url}}

    def _children(
        self,
        node: dict[str, Any],
        depth: int,
        allowed: set[str] | frozenset[str],
    ) -> list[dict[str, Any]]:
        children = node.get("content", [])
        if not isinstance(children, list):
            self._fail("node_invalid", "TipTap node content must be a list")
        return [
            self._node(child, depth=depth + 1, allowed=allowed, parent=node["type"])
            for child in children
        ]

    def _media_source(self, value: object) -> str:
        if not isinstance(value, str) or not value.startswith("media:"):
            self._fail("media_invalid", "TipTap media source is invalid")
        try:
            return f"media:{normalize_ulid(value.removeprefix('media:'))}"
        except (TypeError, ValueError):
            self._fail("media_invalid", "TipTap media source is invalid")

    def _keys(
        self,
        value: dict[str, Any],
        allowed: set[str],
        *,
        required: set[str] | None = None,
        code: str = "attributes_invalid",
    ) -> None:
        if not set(value).issubset(allowed) or not (required or set()).issubset(value):
            self._fail(code, "TipTap document contains unexpected fields")

    def _require_utf8(self, value: str, *, code: str, message: str) -> None:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            self._fail(code, message)

    @staticmethod
    def _fail(code: str, message: str) -> None:
        raise TipTapSchemaError(f"media.tiptap.{code}.v1", message)


__all__ = [
    "CURRENT_TIPTAP_SCHEMA_VERSION",
    "LEGACY_TIPTAP_SCHEMA_VERSION",
    "MAX_TIPTAP_DEPTH",
    "MAX_TIPTAP_NODES",
    "MAX_TIPTAP_TABLE_CELLS",
    "MAX_TIPTAP_TABLE_COLUMNS",
    "MAX_TIPTAP_TABLE_ROWS",
    "NormalizedTipTapDocument",
    "SUPPORTED_TIPTAP_SCHEMA_VERSIONS",
    "TIPTAP_CODE_LANGUAGES",
    "TIPTAP_SCHEMA_FINGERPRINT",
    "TipTapSchemaError",
    "normalize_tiptap_document",
]
