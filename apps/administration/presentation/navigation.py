from dataclasses import dataclass

from apps.navigation.public import AdminNavigationNode, AdminNavigationTree


@dataclass(frozen=True, slots=True)
class NavigationParentOption:
    value: str
    label: str
    selected: bool


@dataclass(frozen=True, slots=True)
class AdminNavigationRow:
    node: AdminNavigationNode
    children: tuple["AdminNavigationRow", ...]
    parent_options: tuple[NavigationParentOption, ...]
    subtree_count: int


def _descendants(node: AdminNavigationNode) -> tuple[AdminNavigationNode, ...]:
    return tuple(
        descendant
        for child in node.children
        for descendant in (child, *_descendants(child))
    )


def admin_navigation_rows(
    tree: AdminNavigationTree,
) -> tuple[AdminNavigationRow, ...]:
    def build(node: AdminNavigationNode) -> AdminNavigationRow:
        descendants = _descendants(node)
        excluded = {node.id, *(item.id for item in descendants)}
        subtree_height = max(
            (item.depth - node.depth for item in descendants),
            default=0,
        )
        options = [
            NavigationParentOption(
                value="",
                label="顶层",
                selected=node.parent_id is None,
            )
        ]
        options.extend(
            NavigationParentOption(
                value=str(candidate.id),
                label=f"{'— ' * candidate.depth}{candidate.label}",
                selected=node.parent_id == candidate.id,
            )
            for candidate in tree.flat_nodes
            if candidate.id not in excluded
            and candidate.depth + 1 + subtree_height <= 2
        )
        return AdminNavigationRow(
            node=node,
            children=tuple(build(child) for child in node.children),
            parent_options=tuple(options),
            subtree_count=1 + len(descendants),
        )

    return tuple(build(root) for root in tree.roots)


__all__ = [
    "AdminNavigationRow",
    "NavigationParentOption",
    "admin_navigation_rows",
]
