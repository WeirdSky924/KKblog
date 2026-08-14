from uuid import uuid4

import pytest
from django.template.loader import render_to_string
from django.urls import reverse

from apps.accounts.models import Account, RoleAssignment
from apps.administration.forms.navigation import (
    NavigationNodeCreateForm,
    NavigationNodeEditConfirmationForm,
)
from apps.navigation.models import NavigationNode, NavigationTreeState
from apps.navigation.presentation import provider as navigation_provider
from apps.navigation.public import NavigationCommandError, NavigationItem
from apps.navigation.queries import (
    invalidate_public_navigation_cache,
    public_navigation_tree,
)
from apps.navigation.services import (
    delete_navigation_subtree,
    edit_navigation_node,
    move_navigation_subtree,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _administrator() -> Account:
    account = Account.objects.create_account(
        email=f"navigation-expand-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    RoleAssignment.objects.bulk_create(
        (
            RoleAssignment(account=account, role=RoleAssignment.Role.AUTHOR),
            RoleAssignment(
                account=account,
                role=RoleAssignment.Role.ADMINISTRATOR,
            ),
        )
    )
    return account


def _internal(
    label: str,
    *,
    position: int,
    parent: NavigationNode | None = None,
    default_expanded: bool = False,
) -> NavigationNode:
    return NavigationNode.objects.create(
        label=label,
        node_type=NavigationNode.NodeType.INTERNAL_PAGE,
        target_url=reverse("public:about"),
        target_id=None,
        parent=parent,
        position=position,
        depth=0 if parent is None else parent.depth + 1,
        default_expanded=default_expanded,
    )


def _versions() -> dict[str, int]:
    return {str(node.id): node.row_version for node in NavigationNode.objects.all()}


def test_only_a_parent_can_enable_default_expansion() -> None:
    actor = _administrator()
    parent = _internal("学习资料", position=0)
    _internal("关于本站", parent=parent, position=0)
    leaf = _internal("独立页面", position=1)
    state = NavigationTreeState.objects.get(pk=1)

    with pytest.raises(NavigationCommandError) as captured:
        edit_navigation_node(
            actor_id=actor.id,
            node_id=leaf.id,
            expected_row_version=leaf.row_version,
            label=leaf.label,
            node_type=leaf.node_type,
            target_url=leaf.target_url,
            target_id=None,
            default_expanded=True,
            expected_tree_version=state.row_version,
            trace_code=f"trc_{'a' * 26}",
            client_ip="127.0.0.1",
        )
    assert captured.value.code == "navigation.default_expanded_leaf.v1"

    result = edit_navigation_node(
        actor_id=actor.id,
        node_id=parent.id,
        expected_row_version=parent.row_version,
        label=parent.label,
        node_type=parent.node_type,
        target_url=parent.target_url,
        target_id=None,
        default_expanded=True,
        expected_tree_version=state.row_version,
        trace_code=f"trc_{'b' * 26}",
        client_ip="127.0.0.1",
    )
    parent.refresh_from_db()
    assert parent.default_expanded is True
    assert result.tree_version == state.row_version + 1


def test_moving_the_last_child_resets_the_former_parent() -> None:
    actor = _administrator()
    parent = _internal("学习资料", position=0, default_expanded=True)
    child = _internal("关于本站", parent=parent, position=0)
    destination = _internal("更多内容", position=1)
    state = NavigationTreeState.objects.get(pk=1)

    move_navigation_subtree(
        actor_id=actor.id,
        node_id=child.id,
        new_parent_id=destination.id,
        new_position=0,
        expected_versions=_versions(),
        expected_tree_version=state.row_version,
        trace_code=f"trc_{'c' * 26}",
        client_ip="127.0.0.1",
    )

    parent.refresh_from_db()
    child.refresh_from_db()
    assert parent.default_expanded is False
    assert child.parent_id == destination.id


def test_deleting_the_last_child_resets_the_parent() -> None:
    actor = _administrator()
    parent = _internal("学习资料", position=0, default_expanded=True)
    child = _internal("关于本站", parent=parent, position=0)
    state = NavigationTreeState.objects.get(pk=1)

    delete_navigation_subtree(
        actor_id=actor.id,
        node_id=child.id,
        expected_versions=_versions(),
        expected_tree_version=state.row_version,
        trace_code=f"trc_{'d' * 26}",
        client_ip="127.0.0.1",
    )

    parent.refresh_from_db()
    assert parent.default_expanded is False


def test_public_query_and_site_presentation_preserve_default_expansion(
    monkeypatch,
) -> None:
    parent = _internal("学习资料", position=0, default_expanded=True)
    _internal("关于本站", parent=parent, position=0)
    invalidate_public_navigation_cache()

    items = public_navigation_tree()
    assert len(items) == 1
    assert items[0].default_expanded is True
    assert items[0].children[0].default_expanded is False

    monkeypatch.setattr(navigation_provider, "public_navigation_tree", lambda: items)
    monkeypatch.setattr(
        navigation_provider,
        "static_page_is_published",
        lambda _page_type: True,
    )
    presentation = navigation_provider.database_site_presentation()
    assert presentation.navigation[0].default_expanded is True


def test_parent_links_and_group_controls_render_as_separate_actions() -> None:
    child = NavigationItem(
        label="关于本站",
        url=reverse("public:about"),
        key=str(uuid4()),
    )
    linked_parent = NavigationItem(
        label="站点内容",
        url=reverse("public:privacy"),
        children=(child,),
        key=str(uuid4()),
        default_expanded=False,
    )
    linked_html = render_to_string(
        "components/navigation/navigation_items.html",
        {
            "items": (linked_parent,),
            "nested": False,
            "home_section_switching": False,
            "active_home_section_id": None,
        },
    )
    assert 'class="public-navigation__row"' in linked_html
    assert f'href="{reverse("public:privacy")}"' in linked_html
    assert "data-navigation-branch-toggle" in linked_html
    assert 'aria-expanded="false"' in linked_html
    assert "data-navigation-children" in linked_html
    assert " hidden" in linked_html

    group = NavigationItem(
        label="站点信息",
        url=None,
        children=(child,),
        key=str(uuid4()),
        default_expanded=True,
    )
    group_html = render_to_string(
        "components/navigation/navigation_items.html",
        {
            "items": (group,),
            "nested": False,
            "home_section_switching": False,
            "active_home_section_id": None,
        },
    )
    assert 'class="public-navigation__group-label"' in group_html
    assert 'aria-expanded="true"' in group_html
    assert group_html.count("<a") == 1


def test_leaf_dto_and_admin_forms_do_not_offer_an_invalid_enabled_state() -> None:
    with pytest.raises(ValueError, match="leaf"):
        NavigationItem(
            label="独立页面",
            url=reverse("public:about"),
            key=str(uuid4()),
            default_expanded=True,
        )

    create_form = NavigationNodeCreateForm(
        section_choices=(),
        parent_choices=(),
    )
    assert create_form.fields["default_expanded"].disabled is True

    leaf_form = NavigationNodeEditConfirmationForm(
        section_choices=(),
        default_expanded_enabled=False,
    )
    parent_form = NavigationNodeEditConfirmationForm(
        section_choices=(),
        default_expanded_enabled=True,
    )
    assert leaf_form.fields["default_expanded"].disabled is True
    assert parent_form.fields["default_expanded"].disabled is False
