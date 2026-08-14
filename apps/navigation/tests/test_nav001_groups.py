from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.urls import reverse

from apps.accounts.models import Account, RoleAssignment
from apps.administration.forms.navigation import NavigationNodeCreateForm
from apps.navigation.models import NavigationNode, NavigationTreeState
from apps.navigation.presentation import provider as navigation_provider
from apps.navigation.public import NavigationCommandError, NavigationItem
from apps.navigation.queries import (
    invalidate_public_navigation_cache,
    public_navigation_tree,
)
from apps.navigation.services import create_navigation_node

pytestmark = pytest.mark.django_db(transaction=True)


def _administrator() -> Account:
    account = Account.objects.create_account(
        email=f"navigation-{uuid4()}@kaj.test",
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


def _create_group(*, position: int = 0) -> NavigationNode:
    return NavigationNode.objects.create(
        label="学习主题",
        node_type="GROUP",
        target_url=None,
        target_id=None,
        parent=None,
        position=position,
        depth=0,
    )


def test_group_target_shape_is_enforced_by_service_and_database() -> None:
    actor = _administrator()
    state = NavigationTreeState.objects.get(pk=1)

    created = create_navigation_node(
        actor_id=actor.id,
        label="学习主题",
        node_type="GROUP",
        target_url=None,
        target_id=None,
        position=0,
        expected_tree_version=state.row_version,
        trace_code=f"trc_{'a' * 26}",
        client_ip="127.0.0.1",
    )
    node = NavigationNode.objects.get(pk=created.node_id)
    assert node.node_type == NavigationNode.NodeType.GROUP
    assert node.target_url is None
    assert node.target_id is None

    with pytest.raises(NavigationCommandError) as captured:
        create_navigation_node(
            actor_id=actor.id,
            label="非法分组",
            node_type="GROUP",
            target_url=reverse("public:about"),
            target_id=None,
            position=1,
            expected_tree_version=created.tree_version,
            trace_code=f"trc_{'b' * 26}",
            client_ip="127.0.0.1",
        )
    assert captured.value.code == "navigation.group_target_invalid.v1"

    with pytest.raises(IntegrityError), transaction.atomic():
        NavigationNode.objects.create(
            label="绕过服务的非法分组",
            node_type="GROUP",
            target_url=reverse("public:about"),
            target_id=None,
            parent=None,
            position=1,
            depth=0,
        )


def test_group_form_accepts_no_target_and_rejects_submitted_target() -> None:
    base = {
        "label": "学习主题",
        "node_type": "GROUP",
        "section_id": "",
        "parent_id": "",
        "position": "0",
        "expected_tree_version": "1",
    }
    valid = NavigationNodeCreateForm(
        data=base | {"target_url": ""},
        section_choices=(),
        parent_choices=(),
    )
    assert valid.is_valid(), valid.errors

    invalid = NavigationNodeCreateForm(
        data=base | {"target_url": reverse("public:about")},
        section_choices=(),
        parent_choices=(),
    )
    assert not invalid.is_valid()
    assert "target_url" in invalid.errors


def test_public_group_requires_a_visible_child_and_tracks_move_or_delete() -> None:
    group = _create_group()
    invalidate_public_navigation_cache()
    assert public_navigation_tree() == ()

    child = NavigationNode.objects.create(
        label="关于本站",
        node_type=NavigationNode.NodeType.INTERNAL_PAGE,
        target_url=reverse("public:about"),
        target_id=None,
        parent=group,
        position=0,
        depth=1,
    )
    invalidate_public_navigation_cache()
    items = public_navigation_tree()
    assert len(items) == 1
    assert items[0].label == "学习主题"
    assert items[0].url is None
    assert tuple(item.label for item in items[0].children) == ("关于本站",)

    child.hidden = True
    child.save(update_fields=("hidden", "updated_at"))
    invalidate_public_navigation_cache()
    assert public_navigation_tree() == ()

    child.hidden = False
    child.parent = None
    child.position = 1
    child.depth = 0
    child.save(update_fields=("hidden", "parent", "position", "depth", "updated_at"))
    invalidate_public_navigation_cache()
    moved = public_navigation_tree()
    assert tuple(item.label for item in moved) == ("关于本站",)

    child.delete()
    invalidate_public_navigation_cache()
    assert public_navigation_tree() == ()


def test_group_navigation_item_renders_as_text_instead_of_empty_link() -> None:
    child = NavigationItem(label="关于本站", url=reverse("public:about"))
    group = NavigationItem(label="学习主题", url=None, children=(child,))

    html = render_to_string(
        "components/navigation/navigation_items.html",
        {
            "items": (group,),
            "nested": False,
            "home_section_switching": False,
            "active_home_section_id": None,
        },
    )

    assert 'class="public-navigation__group-label"' in html
    assert html.count("<a") == 1
    assert 'href=""' not in html


def test_navigation_item_rejects_an_empty_group() -> None:
    with pytest.raises(ValueError, match="children"):
        NavigationItem(label="空分组", url=None)


def test_site_presentation_drops_group_when_its_last_child_is_filtered(
    monkeypatch,
) -> None:
    about = NavigationItem(label="关于本站", url=reverse("public:about"))
    group = NavigationItem(label="站点信息", url=None, children=(about,))
    monkeypatch.setattr(
        navigation_provider,
        "public_navigation_tree",
        lambda: (group,),
    )
    monkeypatch.setattr(
        navigation_provider,
        "static_page_is_published",
        lambda page_type: page_type != "ABOUT",
    )

    presentation = navigation_provider.database_site_presentation()

    assert presentation.navigation == ()
