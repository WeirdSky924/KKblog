import json
from dataclasses import dataclass, replace
from urllib.parse import urlsplit
from uuid import UUID

from django.core.cache import cache
from django.urls import reverse

from apps.accounts.public import is_administrator
from apps.content.public import section_list

from ..models import NavigationNode, NavigationTreeState
from ..public import NavigationItem
from ..validators import (
    normalize_external_navigation_url,
    normalize_internal_navigation_url,
)

PUBLIC_NAVIGATION_CACHE_KEY = "kaj:navigation:public-tree:v1"
PUBLIC_NAVIGATION_CACHE_SECONDS = 300


class NavigationTreeQueryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AdminNavigationNode:
    id: UUID
    label: str
    node_type: str
    node_type_label: str
    target_url: str | None
    target_id: str | None
    target_label: str
    target_missing: bool
    parent_id: UUID | None
    position: int
    depth: int
    hidden: bool
    default_expanded: bool
    row_version: int
    children: tuple["AdminNavigationNode", ...] = ()


@dataclass(frozen=True, slots=True)
class AdminNavigationTree:
    tree_version: int
    roots: tuple[AdminNavigationNode, ...]
    flat_nodes: tuple[AdminNavigationNode, ...]
    version_snapshot: str


def _state_version() -> int:
    try:
        return int(
            NavigationTreeState.objects.only("row_version").get(pk=1).row_version
        )
    except NavigationTreeState.DoesNotExist:
        raise NavigationTreeQueryError("Navigation tree state is missing") from None


def _target(node: NavigationNode, sections: dict[str, str]) -> tuple[str, bool]:
    if node.node_type == NavigationNode.NodeType.GROUP:
        return "无链接，仅用于分组", False
    if node.node_type == NavigationNode.NodeType.SECTION:
        label = sections.get(node.target_id or "")
        return (label or "分区已删除", label is None)
    try:
        if node.node_type == NavigationNode.NodeType.INTERNAL_PAGE:
            return normalize_internal_navigation_url(node.target_url or ""), False
        value = normalize_external_navigation_url(node.target_url or "")
        return urlsplit(value).hostname or value, False
    except ValueError:
        return "目标已失效", True


def _flat_items(rows: tuple[NavigationNode, ...]) -> dict[UUID, AdminNavigationNode]:
    sections = {str(item.section_id): item.name for item in section_list()}
    items = {}
    for row in rows:
        target_label, target_missing = _target(row, sections)
        items[row.id] = AdminNavigationNode(
            id=row.id,
            label=row.label,
            node_type=row.node_type,
            node_type_label=row.get_node_type_display(),
            target_url=row.target_url,
            target_id=row.target_id,
            target_label=target_label,
            target_missing=target_missing,
            parent_id=row.parent_id,
            position=row.position,
            depth=row.depth,
            hidden=row.hidden,
            default_expanded=row.default_expanded,
            row_version=row.row_version,
        )
    return items


def _assemble(
    rows: tuple[NavigationNode, ...],
) -> tuple[tuple[AdminNavigationNode, ...], tuple[AdminNavigationNode, ...]]:
    items = _flat_items(rows)
    children: dict[UUID | None, list[AdminNavigationNode]] = {}
    for item in items.values():
        if item.parent_id is not None and item.parent_id not in items:
            raise NavigationTreeQueryError("Navigation tree has a missing parent")
        children.setdefault(item.parent_id, []).append(item)
    for siblings in children.values():
        siblings.sort(key=lambda item: (item.position, str(item.id)))
        if [item.position for item in siblings] != list(range(len(siblings))):
            raise NavigationTreeQueryError(
                "Navigation sibling ordering is not continuous"
            )

    visited: set[UUID] = set()
    active: set[UUID] = set()

    def build(item: AdminNavigationNode, expected_depth: int) -> AdminNavigationNode:
        if item.id in active:
            raise NavigationTreeQueryError("Navigation tree contains a cycle")
        if item.depth != expected_depth or expected_depth > 2:
            raise NavigationTreeQueryError("Navigation tree depth is invalid")
        active.add(item.id)
        nested = tuple(
            build(child, expected_depth + 1) for child in children.get(item.id, ())
        )
        active.remove(item.id)
        visited.add(item.id)
        return replace(item, children=nested)

    roots = tuple(build(item, 0) for item in children.get(None, ()))
    if visited != set(items):
        raise NavigationTreeQueryError("Navigation tree contains unreachable nodes")

    flattened: list[AdminNavigationNode] = []

    def append(item: AdminNavigationNode) -> None:
        flattened.append(item)
        for child in item.children:
            append(child)

    for root in roots:
        append(root)
    return roots, tuple(flattened)


def _tree() -> AdminNavigationTree:
    for _attempt in range(3):
        before_version = _state_version()
        rows = tuple(
            NavigationNode.objects.all().order_by(
                "depth", "parent_id", "position", "id"
            )
        )
        after_version = _state_version()
        if before_version == after_version:
            roots, flat_nodes = _assemble(rows)
            versions = json.dumps(
                {str(item.id): item.row_version for item in flat_nodes},
                separators=(",", ":"),
                sort_keys=True,
            )
            return AdminNavigationTree(
                after_version,
                roots,
                flat_nodes,
                versions,
            )
    raise NavigationTreeQueryError("Navigation tree changed during query")


def admin_navigation_tree(*, actor_id) -> AdminNavigationTree:
    if not is_administrator(actor_id):
        raise PermissionError("Administrator navigation access denied")
    return _tree()


def _public_item(node: AdminNavigationNode) -> NavigationItem | None:
    if node.hidden or node.target_missing:
        return None
    children = tuple(
        child for source in node.children if (child := _public_item(source)) is not None
    )
    if node.node_type == NavigationNode.NodeType.GROUP:
        if not children:
            return None
        url = None
    elif node.node_type == NavigationNode.NodeType.SECTION:
        url = reverse("public:section", kwargs={"section_id": node.target_id})
    else:
        url = node.target_url or ""
    return NavigationItem(
        label=node.label,
        url=url,
        children=children,
        key=str(node.id),
        section_id=node.target_id
        if node.node_type == NavigationNode.NodeType.SECTION
        else None,
        default_expanded=node.default_expanded and bool(children),
    )


def public_navigation_tree() -> tuple[NavigationItem, ...]:
    cached = cache.get(PUBLIC_NAVIGATION_CACHE_KEY)
    current_version = _state_version()
    if (
        isinstance(cached, tuple)
        and len(cached) == 2
        and cached[0] == current_version
        and isinstance(cached[1], tuple)
        and all(isinstance(item, NavigationItem) for item in cached[1])
    ):
        return cached[1]
    for _attempt in range(3):
        tree = _tree()
        items = tuple(
            item for root in tree.roots if (item := _public_item(root)) is not None
        )
        if _state_version() == tree.tree_version:
            cache.set(
                PUBLIC_NAVIGATION_CACHE_KEY,
                (tree.tree_version, items),
                PUBLIC_NAVIGATION_CACHE_SECONDS,
            )
            return items
        cache.delete(PUBLIC_NAVIGATION_CACHE_KEY)
    raise NavigationTreeQueryError("Navigation tree changed during cache fill")


def invalidate_public_navigation_cache() -> None:
    cache.delete(PUBLIC_NAVIGATION_CACHE_KEY)


__all__ = [
    "AdminNavigationNode",
    "AdminNavigationTree",
    "NavigationTreeQueryError",
    "admin_navigation_tree",
    "invalidate_public_navigation_cache",
    "public_navigation_tree",
]
