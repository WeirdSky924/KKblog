import json
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from django.db import transaction
from django.db.models import F

from apps.accounts.public import is_administrator
from apps.content.public import section_by_id
from apps.core.events import enqueue_event
from apps.operations.public import record_audit_entry

from ..events import NAVIGATION_CHANGED
from ..models import NavigationNode, NavigationTreeState
from ..queries import invalidate_public_navigation_cache
from ..validators import (
    normalize_external_navigation_url,
    normalize_internal_navigation_url,
    normalize_navigation_label,
)


class NavigationCommandError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.safe_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class NavigationNodeResult:
    node_id: UUID
    row_version: int
    tree_version: int


@dataclass(frozen=True, slots=True)
class NavigationDeleteResult:
    deleted_node_count: int
    tree_version: int


def _actor(value) -> UUID:
    try:
        actor_id = UUID(str(value))
    except (TypeError, ValueError):
        raise NavigationCommandError(
            "navigation.admin_required.v1", "只有管理员可以管理公共导航。"
        ) from None
    if not is_administrator(actor_id):
        raise NavigationCommandError(
            "navigation.admin_required.v1", "只有管理员可以管理公共导航。"
        )
    return actor_id


def _identity(value, *, code: str = "navigation.node_not_found.v1") -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise NavigationCommandError(code, "导航节点不存在。") from None


def _parent_identity(value) -> UUID | None:
    if value in {None, ""}:
        return None
    return _identity(value, code="navigation.parent_not_found.v1")


def _position(value, *, maximum: int) -> int:
    if isinstance(value, bool):
        raise NavigationCommandError(
            "navigation.position_invalid.v1", "导航位置不合法。"
        )
    try:
        position = int(value)
    except (TypeError, ValueError):
        raise NavigationCommandError(
            "navigation.position_invalid.v1", "导航位置不合法。"
        ) from None
    if not 0 <= position <= maximum:
        raise NavigationCommandError(
            "navigation.position_invalid.v1", "导航位置超出当前层级范围。"
        )
    return position


def _tree_version(value) -> int:
    if isinstance(value, bool):
        raise NavigationCommandError(
            "navigation.version_invalid.v1", "导航版本不合法。"
        )
    try:
        version = int(value)
    except (TypeError, ValueError):
        raise NavigationCommandError(
            "navigation.version_invalid.v1", "导航版本不合法。"
        ) from None
    if version < 1:
        raise NavigationCommandError(
            "navigation.version_invalid.v1", "导航版本不合法。"
        )
    return version


def _versions(value) -> dict[UUID, int]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            raise NavigationCommandError(
                "navigation.version_invalid.v1", "导航版本快照不合法。"
            ) from None
    if not isinstance(value, dict) or len(value) > 500:
        raise NavigationCommandError(
            "navigation.version_invalid.v1", "导航版本快照不合法。"
        )
    normalized: dict[UUID, int] = {}
    try:
        for key, version in value.items():
            identity = UUID(str(key))
            if isinstance(version, bool) or int(version) < 1:
                raise ValueError
            normalized[identity] = int(version)
    except (TypeError, ValueError):
        raise NavigationCommandError(
            "navigation.version_invalid.v1", "导航版本快照不合法。"
        ) from None
    return normalized


def _target(node_type: str, target_url, target_id) -> tuple[str | None, str | None]:
    if node_type == NavigationNode.NodeType.INTERNAL_PAGE:
        try:
            return normalize_internal_navigation_url(target_url), None
        except ValueError as error:
            raise NavigationCommandError(
                "navigation.internal_target_invalid.v1", str(error)
            ) from None
    if node_type == NavigationNode.NodeType.EXTERNAL_LINK:
        try:
            return normalize_external_navigation_url(target_url), None
        except ValueError as error:
            raise NavigationCommandError(
                "navigation.external_target_invalid.v1", str(error)
            ) from None
    if node_type != NavigationNode.NodeType.SECTION:
        raise NavigationCommandError(
            "navigation.node_type_invalid.v1", "导航节点类型不合法。"
        )
    identity = _identity(target_id, code="navigation.section_target_invalid.v1")
    if section_by_id(identity) is None:
        raise NavigationCommandError(
            "navigation.section_target_invalid.v1", "目标文章分区不存在。"
        )
    return None, str(identity)


def _lock_tree() -> tuple[NavigationTreeState, list[NavigationNode]]:
    try:
        state = NavigationTreeState.objects.select_for_update().get(pk=1)
    except NavigationTreeState.DoesNotExist:
        raise NavigationCommandError(
            "navigation.tree_state_missing.v1", "公共导航状态不可用。"
        ) from None
    nodes = list(NavigationNode.objects.select_for_update().order_by("id"))
    return state, nodes


def _check_tree_version(state: NavigationTreeState, expected) -> None:
    if state.row_version != _tree_version(expected):
        raise NavigationCommandError(
            "navigation.edit_conflict.v1", "公共导航已被其他操作更新，请刷新后重试。"
        )


def _node_map(nodes: list[NavigationNode]) -> dict[UUID, NavigationNode]:
    return {node.id: node for node in nodes}


def _children(nodes: list[NavigationNode]) -> dict[UUID | None, list[NavigationNode]]:
    grouped: dict[UUID | None, list[NavigationNode]] = {}
    for node in nodes:
        grouped.setdefault(node.parent_id, []).append(node)
    for siblings in grouped.values():
        siblings.sort(key=lambda node: (node.position, str(node.id)))
    return grouped


def _descendants(
    node_id: UUID, grouped: dict[UUID | None, list[NavigationNode]]
) -> list[NavigationNode]:
    result: list[NavigationNode] = []
    stack = list(reversed(grouped.get(node_id, ())))
    while stack:
        node = stack.pop()
        result.append(node)
        stack.extend(reversed(grouped.get(node.id, ())))
    return result


def _snapshot(node: NavigationNode) -> dict[str, object]:
    if node.node_type == NavigationNode.NodeType.EXTERNAL_LINK:
        parsed = urlsplit(node.target_url or "")
        target_ref = parsed.hostname or "external"
    else:
        target_ref = node.target_id or node.target_url or ""
    return {
        "label": node.label,
        "node_type": node.node_type,
        "parent_id": str(node.parent_id) if node.parent_id else None,
        "position": node.position,
        "depth": node.depth,
        "hidden": node.hidden,
        "target_ref": target_ref,
        "row_version": node.row_version,
    }


def _advance(
    state: NavigationTreeState,
    *,
    actor_id: UUID,
    trace_code: str,
    action: str,
) -> int:
    state.row_version += 1
    state.save(update_fields=("row_version", "updated_at"))
    enqueue_event(
        NAVIGATION_CHANGED,
        aggregate_type="navigation_tree",
        aggregate_id="public",
        actor_id=actor_id,
        trace_code=trace_code,
        payload={"action": action, "tree_version": state.row_version},
    )
    transaction.on_commit(invalidate_public_navigation_cache)
    return state.row_version


def _parent(
    nodes: dict[UUID, NavigationNode], parent_id: UUID | None
) -> NavigationNode | None:
    if parent_id is None:
        return None
    parent = nodes.get(parent_id)
    if parent is None:
        raise NavigationCommandError(
            "navigation.parent_not_found.v1", "父级导航节点不存在。"
        )
    return parent


def _expected_versions(nodes: list[NavigationNode], submitted: dict[UUID, int]) -> None:
    current = {node.id: node.row_version for node in nodes}
    if current != submitted:
        raise NavigationCommandError(
            "navigation.edit_conflict.v1", "公共导航已被其他操作更新，请刷新后重试。"
        )


def _ordered_siblings(
    nodes: list[NavigationNode], parent_id: UUID | None
) -> list[NavigationNode]:
    return sorted(
        (node for node in nodes if node.parent_id == parent_id),
        key=lambda node: (node.position, str(node.id)),
    )


def _temporary_positions(nodes: list[NavigationNode]) -> None:
    if not nodes:
        return
    offset = max(node.position for node in nodes) + len(nodes) + 1
    NavigationNode.objects.filter(pk__in=(node.id for node in nodes)).update(
        position=F("position") + offset
    )


def _save_positions(nodes: list[NavigationNode]) -> None:
    for position, node in enumerate(nodes):
        node.position = position
        node.row_version += 1
        node.save(update_fields=("position", "row_version", "updated_at"))


def create_navigation_node(
    *,
    actor_id,
    label: str,
    node_type: str,
    target_url=None,
    target_id=None,
    parent_id=None,
    position=None,
    expected_tree_version,
    trace_code: str,
    client_ip: str,
) -> NavigationNodeResult:
    actor = _actor(actor_id)
    try:
        normalized_label = normalize_navigation_label(label)
    except ValueError as error:
        raise NavigationCommandError(
            "navigation.label_invalid.v1", str(error)
        ) from None
    normalized_url, normalized_id = _target(node_type, target_url, target_id)
    parent_identity = _parent_identity(parent_id)
    with transaction.atomic():
        state, locked = _lock_tree()
        _check_tree_version(state, expected_tree_version)
        nodes = _node_map(locked)
        parent = _parent(nodes, parent_identity)
        depth = 0 if parent is None else parent.depth + 1
        if depth > 2:
            raise NavigationCommandError(
                "navigation.depth_exceeded.v1", "公共导航最多支持三层。"
            )
        siblings = _ordered_siblings(locked, parent_identity)
        target_position = _position(
            len(siblings) if position in {None, ""} else position,
            maximum=len(siblings),
        )
        shifted = siblings[target_position:]
        shifted_before = {sibling.id: _snapshot(sibling) for sibling in shifted}
        _temporary_positions(shifted)
        for index, sibling in enumerate(shifted, target_position + 1):
            sibling.position = index
            sibling.row_version += 1
            sibling.save(update_fields=("position", "row_version", "updated_at"))
        node = NavigationNode.objects.create(
            label=normalized_label,
            node_type=node_type,
            target_url=normalized_url,
            target_id=normalized_id,
            parent_id=parent_identity,
            position=target_position,
            depth=depth,
        )
        record_audit_entry(
            action="navigation.node.create",
            actor_id=actor,
            target_id=str(node.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before={},
            after=_snapshot(node),
            summary="Create public navigation node",
        )
        for sibling in shifted:
            record_audit_entry(
                action="navigation.node.create",
                actor_id=actor,
                target_id=str(sibling.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before=shifted_before[sibling.id],
                after=_snapshot(sibling),
                summary="Reorder public navigation after node creation",
            )
        tree_version = _advance(
            state,
            actor_id=actor,
            trace_code=trace_code,
            action="created",
        )
    return NavigationNodeResult(node.id, node.row_version, tree_version)


def edit_navigation_node(
    *,
    actor_id,
    node_id,
    expected_row_version,
    label: str,
    node_type: str,
    target_url=None,
    target_id=None,
    expected_tree_version,
    trace_code: str,
    client_ip: str,
) -> NavigationNodeResult:
    actor = _actor(actor_id)
    identity = _identity(node_id)
    try:
        normalized_label = normalize_navigation_label(label)
    except ValueError as error:
        raise NavigationCommandError(
            "navigation.label_invalid.v1", str(error)
        ) from None
    normalized_url, normalized_id = _target(node_type, target_url, target_id)
    with transaction.atomic():
        state, locked = _lock_tree()
        _check_tree_version(state, expected_tree_version)
        node = _node_map(locked).get(identity)
        if node is None:
            raise NavigationCommandError(
                "navigation.node_not_found.v1", "导航节点不存在。"
            )
        if node.row_version != _tree_version(expected_row_version):
            raise NavigationCommandError(
                "navigation.edit_conflict.v1", "导航节点已被更新，请刷新后重试。"
            )
        before = _snapshot(node)
        node.label = normalized_label
        node.node_type = node_type
        node.target_url = normalized_url
        node.target_id = normalized_id
        node.row_version += 1
        node.save(
            update_fields=(
                "label",
                "node_type",
                "target_url",
                "target_id",
                "row_version",
                "updated_at",
            )
        )
        record_audit_entry(
            action="navigation.node.edit",
            actor_id=actor,
            target_id=str(node.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after=_snapshot(node),
            summary="Edit public navigation node",
        )
        tree_version = _advance(
            state,
            actor_id=actor,
            trace_code=trace_code,
            action="edited",
        )
    return NavigationNodeResult(node.id, node.row_version, tree_version)


def set_navigation_node_hidden(
    *,
    actor_id,
    node_id,
    hidden: bool,
    expected_row_version,
    expected_tree_version,
    trace_code: str,
    client_ip: str,
) -> NavigationNodeResult:
    actor = _actor(actor_id)
    identity = _identity(node_id)
    if type(hidden) is not bool:
        raise NavigationCommandError(
            "navigation.visibility_invalid.v1", "导航显隐状态不合法。"
        )
    with transaction.atomic():
        state, locked = _lock_tree()
        _check_tree_version(state, expected_tree_version)
        node = _node_map(locked).get(identity)
        if node is None:
            raise NavigationCommandError(
                "navigation.node_not_found.v1", "导航节点不存在。"
            )
        if node.row_version != _tree_version(expected_row_version):
            raise NavigationCommandError(
                "navigation.edit_conflict.v1", "导航节点已被更新，请刷新后重试。"
            )
        if node.hidden == hidden:
            raise NavigationCommandError(
                "navigation.visibility_invalid.v1", "导航显隐状态已经变化。"
            )
        before = _snapshot(node)
        node.hidden = hidden
        node.row_version += 1
        node.save(update_fields=("hidden", "row_version", "updated_at"))
        record_audit_entry(
            action="navigation.node.visibility",
            actor_id=actor,
            target_id=str(node.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after=_snapshot(node),
            summary="Change public navigation visibility",
        )
        tree_version = _advance(
            state,
            actor_id=actor,
            trace_code=trace_code,
            action="visibility",
        )
    return NavigationNodeResult(node.id, node.row_version, tree_version)


def move_navigation_subtree(
    *,
    actor_id,
    node_id,
    new_parent_id,
    new_position,
    expected_versions,
    expected_tree_version,
    trace_code: str,
    client_ip: str,
) -> NavigationNodeResult:
    actor = _actor(actor_id)
    identity = _identity(node_id)
    parent_identity = _parent_identity(new_parent_id)
    submitted_versions = _versions(expected_versions)
    with transaction.atomic():
        state, locked = _lock_tree()
        _check_tree_version(state, expected_tree_version)
        nodes = _node_map(locked)
        node = nodes.get(identity)
        if node is None:
            raise NavigationCommandError(
                "navigation.node_not_found.v1", "导航节点不存在。"
            )
        parent = _parent(nodes, parent_identity)
        grouped = _children(locked)
        descendants = _descendants(node.id, grouped)
        subtree = [node, *descendants]
        subtree_ids = {item.id for item in subtree}
        if parent_identity in subtree_ids:
            raise NavigationCommandError(
                "navigation.cycle_detected.v1", "导航节点不能移入自己的子树。"
            )
        new_depth = 0 if parent is None else parent.depth + 1
        relative_depth = max(item.depth - node.depth for item in subtree)
        if new_depth + relative_depth > 2:
            raise NavigationCommandError(
                "navigation.depth_exceeded.v1", "移动后将超过三层导航限制。"
            )

        old_parent_id = node.parent_id
        old_siblings = [
            item for item in grouped.get(old_parent_id, ()) if item.id != node.id
        ]
        if old_parent_id == parent_identity:
            destination = old_siblings
        else:
            destination = list(grouped.get(parent_identity, ()))
        position = _position(new_position, maximum=len(destination))
        final_destination = [*destination]
        final_destination.insert(position, node)
        if old_parent_id == parent_identity and [
            item.id for item in final_destination
        ] == [item.id for item in grouped.get(old_parent_id, ())]:
            raise NavigationCommandError(
                "navigation.position_invalid.v1", "导航节点已经位于该位置。"
            )

        affected = {
            item.id: item
            for item in (
                *subtree,
                *old_siblings,
                *destination,
            )
        }
        expected_subset = {
            item_id: submitted_versions[item_id]
            for item_id in affected
            if item_id in submitted_versions
        }
        _expected_versions(list(affected.values()), expected_subset)
        before = {item.id: _snapshot(item) for item in affected.values()}

        ordered = {
            item.id: item
            for item in (
                *grouped.get(old_parent_id, ()),
                *grouped.get(parent_identity, ()),
            )
        }
        _temporary_positions(list(ordered.values()))
        if old_parent_id != parent_identity:
            for index, sibling in enumerate(old_siblings):
                sibling.position = index
        for index, sibling in enumerate(final_destination):
            sibling.position = index
            sibling.parent_id = parent_identity
        depth_delta = new_depth - node.depth
        for item in subtree:
            item.depth += depth_delta
        for item in affected.values():
            item.row_version += 1
            item.save(
                update_fields=(
                    "parent",
                    "position",
                    "depth",
                    "row_version",
                    "updated_at",
                )
            )
            record_audit_entry(
                action="navigation.node.move",
                actor_id=actor,
                target_id=str(item.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before=before[item.id],
                after=_snapshot(item),
                summary="Move public navigation subtree",
            )
        tree_version = _advance(
            state,
            actor_id=actor,
            trace_code=trace_code,
            action="moved",
        )
    return NavigationNodeResult(node.id, node.row_version, tree_version)


def delete_navigation_subtree(
    *,
    actor_id,
    node_id,
    expected_versions,
    expected_tree_version,
    trace_code: str,
    client_ip: str,
) -> NavigationDeleteResult:
    actor = _actor(actor_id)
    identity = _identity(node_id)
    submitted_versions = _versions(expected_versions)
    with transaction.atomic():
        state, locked = _lock_tree()
        _check_tree_version(state, expected_tree_version)
        nodes = _node_map(locked)
        node = nodes.get(identity)
        if node is None:
            raise NavigationCommandError(
                "navigation.node_not_found.v1", "导航节点不存在。"
            )
        grouped = _children(locked)
        subtree = [node, *_descendants(node.id, grouped)]
        siblings = [
            item for item in grouped.get(node.parent_id, ()) if item.id != node.id
        ]
        affected = {item.id: item for item in (*subtree, *siblings)}
        expected_subset = {
            item_id: submitted_versions[item_id]
            for item_id in affected
            if item_id in submitted_versions
        }
        _expected_versions(list(affected.values()), expected_subset)
        before = {item.id: _snapshot(item) for item in affected.values()}

        for item in subtree:
            record_audit_entry(
                action="navigation.node.delete",
                actor_id=actor,
                target_id=str(item.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before=before[item.id],
                after={"deleted": True},
                summary="Delete public navigation subtree",
            )
        node.delete()
        _temporary_positions(siblings)
        _save_positions(siblings)
        for sibling in siblings:
            record_audit_entry(
                action="navigation.node.delete",
                actor_id=actor,
                target_id=str(sibling.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before=before[sibling.id],
                after=_snapshot(sibling),
                summary="Reorder public navigation after subtree deletion",
            )
        tree_version = _advance(
            state,
            actor_id=actor,
            trace_code=trace_code,
            action="deleted",
        )
    return NavigationDeleteResult(len(subtree), tree_version)


__all__ = [
    "NavigationCommandError",
    "NavigationDeleteResult",
    "NavigationNodeResult",
    "create_navigation_node",
    "delete_navigation_subtree",
    "edit_navigation_node",
    "move_navigation_subtree",
    "set_navigation_node_hidden",
]
