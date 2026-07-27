from datetime import timedelta
from uuid import uuid4

import pytest
from django.apps import apps
from django.utils import timezone

from apps.comments.models import Comment, DiscussionThread
from apps.comments.services import (
    GuestbookSettingsError,
    create_top_level_comment,
    delete_comment_as_owner,
    reply_to_comment,
    sync_guestbook_thread,
    update_guestbook_settings,
)
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code

pytestmark = pytest.mark.django_db(transaction=True)


class _Cooldown:
    def reserve(self, **_kwargs):
        return object()

    def rollback(self, _reservation) -> None:
        return None


def _account(label: str, *, roles: tuple[str, ...] = ()):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    for role in roles:
        role_model.objects.create(account=account, role=role)
    return account


def _visible_comment(thread, author, *, parent=None, root=None, depth=0, body="留言"):
    identity = new_ulid()
    now = timezone.now() - timedelta(minutes=20)
    return Comment.objects.create(
        id=identity,
        thread=thread,
        parent=parent,
        root_id=identity if root is None else root.id,
        author=author,
        author_kind=Comment.AuthorKind.ACCOUNT,
        body=body,
        state=Comment.State.VISIBLE,
        visible_at=now,
        depth=depth,
        reply_count=0,
        client_ip="192.0.2.107",
        created_at=now,
    )


def test_guestbook_singleton_defaults_to_active_administrator_and_keeps_settings() -> (
    None
):
    administrator = _account("cmt007-admin-one", roles=("AUTHOR", "ADMINISTRATOR"))
    successor = _account("cmt007-admin-two", roles=("AUTHOR",))

    thread = sync_guestbook_thread()
    assert thread.target_type == DiscussionThread.TargetType.GUESTBOOK
    assert thread.target_id == "site"
    assert thread.owner_id == administrator.id
    assert thread.comments_enabled is True
    assert thread.view_login_required is False
    assert thread.post_login_required is False
    assert sync_guestbook_thread().id == thread.id

    DiscussionThread.objects.filter(pk=thread.pk).update(
        comments_enabled=False,
        post_login_required=True,
    )
    apps.get_model("accounts", "RoleAssignment").objects.filter(
        role="ADMINISTRATOR"
    ).update(account=successor)
    refreshed = sync_guestbook_thread()
    assert refreshed.id == thread.id
    assert refreshed.owner_id == successor.id
    assert refreshed.comments_enabled is False
    assert refreshed.post_login_required is True


def test_guestbook_settings_require_admin_and_audit_rolls_back_with_command(
    monkeypatch,
) -> None:
    administrator = _account("cmt007-settings-admin", roles=("AUTHOR", "ADMINISTRATOR"))
    member = _account("cmt007-settings-member")
    thread = sync_guestbook_thread()

    with pytest.raises(GuestbookSettingsError) as denied:
        update_guestbook_settings(
            actor_id=member.id,
            comments_enabled=False,
            post_login_required=True,
            client_ip="198.51.100.107",
            trace_code=new_trace_code(),
        )
    assert denied.value.code == "comments.guestbook_manage_forbidden.v1"

    result = update_guestbook_settings(
        actor_id=administrator.id,
        comments_enabled=False,
        post_login_required=True,
        client_ip="198.51.100.108",
        trace_code=new_trace_code(),
    )
    assert result.changed is True
    thread.refresh_from_db()
    assert (thread.comments_enabled, thread.post_login_required) == (False, True)
    audit = apps.get_model("operations", "AuditEntry").objects.get(
        action="comments.guestbook.settings_update"
    )
    assert audit.actor_id == administrator.id
    assert audit.before_safe == {
        "comments_enabled": True,
        "post_login_required": False,
    }
    assert audit.after_safe == {
        "comments_enabled": False,
        "post_login_required": True,
    }

    from apps.comments.services import guestbook as guestbook_service

    monkeypatch.setattr(
        guestbook_service,
        "record_audit_entry",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("audit unavailable")),
    )
    with pytest.raises(RuntimeError, match="audit unavailable"):
        update_guestbook_settings(
            actor_id=administrator.id,
            comments_enabled=True,
            post_login_required=False,
            client_ip="198.51.100.109",
            trace_code=new_trace_code(),
        )
    thread.refresh_from_db()
    assert (thread.comments_enabled, thread.post_login_required) == (False, True)


def test_guestbook_reuses_post_reply_owner_delete_and_deep_alert() -> None:
    administrator = _account("cmt007-flow-admin", roles=("AUTHOR", "ADMINISTRATOR"))
    member = _account("cmt007-flow-member")
    thread = sync_guestbook_thread()
    cooldown = _Cooldown()

    posted = create_top_level_comment(
        target_type="GUESTBOOK",
        target_id="site",
        actor_id=None,
        client_ip="198.51.100.110",
        body="访客留言",
        trace_code=new_trace_code(),
        cooldown_store=cooldown,
    )
    root = Comment.objects.get(pk=posted.comment_id)
    assert root.thread_id == thread.id
    assert root.author_kind == Comment.AuthorKind.ANONYMOUS
    assert root.state == Comment.State.BUFFERED
    Comment.objects.filter(pk=root.pk).update(state=Comment.State.VISIBLE)

    replied = reply_to_comment(
        parent_id=root.id,
        actor_id=member.id,
        client_ip="198.51.100.111",
        body="登录用户回复",
        trace_code=new_trace_code(),
        cooldown_store=cooldown,
    )
    reply = Comment.objects.get(pk=replied.comment_id)
    assert (reply.thread_id, reply.root_id, reply.depth) == (thread.id, root.id, 1)

    deleted = delete_comment_as_owner(
        comment_id=reply.id,
        actor_id=administrator.id,
        client_ip="198.51.100.112",
        trace_code=new_trace_code(),
    )
    assert deleted.deleted_by_kind == Comment.DeletedByKind.OWNER
    reply.refresh_from_db()
    assert (reply.state, reply.body) == (Comment.State.DELETED, "")

    deep_root = _visible_comment(thread, member, body="深层根留言")
    parent = deep_root
    for depth in range(1, 101):
        parent = _visible_comment(
            thread,
            member,
            parent=parent,
            root=deep_root,
            depth=depth,
            body=f"第 {depth} 层",
        )
    deep_reply = reply_to_comment(
        parent_id=parent.id,
        actor_id=member.id,
        client_ip="198.51.100.113",
        body="第 101 层",
        trace_code=new_trace_code(),
        cooldown_store=cooldown,
    )
    assert deep_reply.depth == 101
    event = apps.get_model("core", "OutboxEvent").objects.get(
        event_type="comment.deep_thread.v1",
        aggregate_id=str(thread.id),
    )
    assert event.payload["target_type"] == "GUESTBOOK"
    assert event.payload["target_id"] == "site"
    assert event.payload["owner_id"] == str(administrator.id)
