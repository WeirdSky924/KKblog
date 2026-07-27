from dataclasses import dataclass, field
from datetime import timedelta
from uuid import uuid4

import pytest
from django.apps import apps
from django.utils import timezone

from apps.comments.models import Comment, DiscussionThread
from apps.comments.services.deletion import (
    CommentDeletionError,
    delete_comment_as_admin,
    delete_comment_as_owner,
    delete_own_comment,
)
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.operations.public import AuditRejected

pytestmark = pytest.mark.django_db(transaction=True)


@dataclass
class _Policy:
    active_ids: set = field(default_factory=set)
    administrator_ids: set = field(default_factory=set)
    blocked_ips: set[str] = field(default_factory=set)

    def is_active_account(self, account_id):
        return account_id in self.active_ids

    def is_administrator(self, account_id):
        return account_id in self.administrator_ids

    def is_ip_blocked(self, client_ip):
        return client_ip in self.blocked_ips


@dataclass
class _Media:
    asset_ids: tuple[str, ...] = ()
    fail: bool = False
    calls: list[str] = field(default_factory=list)

    def release_images(self, comment_id: str) -> tuple[str, ...]:
        self.calls.append(comment_id)
        if self.fail:
            raise RuntimeError("isolated media failure")
        return self.asset_ids


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


def _thread(owner) -> DiscussionThread:
    return DiscussionThread.objects.create(
        target_type="ARTICLE",
        target_id=new_ulid(),
        owner=owner,
    )


def _comment(
    thread,
    author,
    *,
    parent=None,
    root=None,
    depth=0,
    author_kind=Comment.AuthorKind.ACCOUNT,
    body="待删除评论",
) -> Comment:
    comment_id = new_ulid()
    now = timezone.now() - timedelta(minutes=20)
    return Comment.objects.create(
        id=comment_id,
        thread=thread,
        parent=parent,
        root_id=comment_id if root is None else root.id,
        author=author,
        author_kind=author_kind,
        body=body,
        state=Comment.State.VISIBLE,
        visible_at=now,
        depth=depth,
        reply_count=1 if root is None else 0,
        client_ip="192.0.2.80",
        created_at=now,
    )


def test_self_delete_rechecks_identity_network_and_preserves_children() -> None:
    owner = _account("cmt006-self-owner")
    member = _account("cmt006-self-member")
    stranger = _account("cmt006-self-stranger")
    thread = _thread(owner)
    root = _comment(thread, member)
    child = _comment(thread, owner, parent=root, root=root, depth=1, body="保留的回复")
    policy = _Policy({owner.id, member.id, stranger.id})
    media = _Media((new_ulid(),))

    with pytest.raises(CommentDeletionError) as guest:
        delete_own_comment(
            comment_id=root.id,
            actor_id=None,
            client_ip="198.51.100.80",
            trace_code=new_trace_code(),
            account_policy=policy,
            media_gateway=media,
        )
    assert guest.value.code == "comments.login_required.v1"

    with pytest.raises(CommentDeletionError) as forged:
        delete_own_comment(
            comment_id=root.id,
            actor_id=stranger.id,
            client_ip="198.51.100.80",
            trace_code=new_trace_code(),
            account_policy=policy,
            media_gateway=media,
        )
    assert forged.value.code == "comments.delete_not_allowed.v1"

    policy.blocked_ips.add("198.51.100.81")
    with pytest.raises(CommentDeletionError) as blocked:
        delete_own_comment(
            comment_id=root.id,
            actor_id=member.id,
            client_ip="198.51.100.81",
            trace_code=new_trace_code(),
            account_policy=policy,
            media_gateway=media,
        )
    assert blocked.value.code == "comments.network_restricted.v1"

    result = delete_own_comment(
        comment_id=root.id,
        actor_id=member.id,
        client_ip="198.51.100.80",
        trace_code=new_trace_code(),
        account_policy=policy,
        media_gateway=media,
    )
    root.refresh_from_db()
    child.refresh_from_db()
    assert result.changed is True
    assert result.asset_ids == media.asset_ids
    assert result.recipient_ids == ()
    assert (root.state, root.body, root.deleted_by_kind) == (
        Comment.State.DELETED,
        "",
        Comment.DeletedByKind.SELF,
    )
    assert child.state == Comment.State.VISIBLE
    assert child.parent_id == root.id

    duplicate = delete_own_comment(
        comment_id=root.id,
        actor_id=member.id,
        client_ip="198.51.100.80",
        trace_code=new_trace_code(),
        account_policy=policy,
        media_gateway=media,
    )
    assert duplicate.changed is False
    assert media.calls == [root.id]
    event_model = apps.get_model("core", "OutboxEvent")
    assert (
        event_model.objects.filter(
            event_type="comment.deleted.v1", aggregate_id=root.id
        ).count()
        == 1
    )


def test_owner_delete_requires_thread_owner_and_media_failure_rolls_back() -> None:
    owner = _account("cmt006-owner")
    member = _account("cmt006-owner-member")
    outsider = _account("cmt006-owner-outsider")
    thread = _thread(owner)
    comment = _comment(thread, member)
    policy = _Policy({owner.id, member.id, outsider.id})

    with pytest.raises(CommentDeletionError) as forged:
        delete_comment_as_owner(
            comment_id=comment.id,
            actor_id=outsider.id,
            client_ip="198.51.100.82",
            trace_code=new_trace_code(),
            account_policy=policy,
            media_gateway=_Media(),
        )
    assert forged.value.code == "comments.delete_not_allowed.v1"

    with pytest.raises(CommentDeletionError) as media_failure:
        delete_comment_as_owner(
            comment_id=comment.id,
            actor_id=owner.id,
            client_ip="198.51.100.82",
            trace_code=new_trace_code(),
            account_policy=policy,
            media_gateway=_Media(fail=True),
        )
    assert media_failure.value.code == "comments.media_cleanup_failed.v1"
    comment.refresh_from_db()
    assert comment.state == Comment.State.VISIBLE
    assert (
        not apps.get_model("core", "OutboxEvent")
        .objects.filter(aggregate_id=comment.id)
        .exists()
    )


def test_admin_delete_audits_safe_state_and_deduplicates_recipients() -> None:
    owner = _account("cmt006-admin-owner")
    administrator = _account("cmt006-admin", roles=("ADMINISTRATOR",))
    thread = _thread(owner)
    comment = _comment(thread, owner)
    asset_ids = (new_ulid(), new_ulid())
    policy = _Policy(
        {owner.id, administrator.id},
        {administrator.id},
    )

    result = delete_comment_as_admin(
        comment_id=comment.id,
        actor_id=administrator.id,
        client_ip="198.51.100.83",
        reason="违反评论规则",
        trace_code=new_trace_code(),
        account_policy=policy,
        media_gateway=_Media(asset_ids),
    )
    assert result.recipient_ids == (owner.id,)
    comment.refresh_from_db()
    assert comment.deletion_reason == "违反评论规则"
    audit = apps.get_model("operations", "AuditEntry").objects.get(
        action="comments.comment.admin_delete",
        target_id=comment.id,
    )
    assert audit.client_ip == "198.51.100.83"
    assert "body" not in str(audit.before_safe).casefold()
    assert "body" not in str(audit.after_safe).casefold()
    event = apps.get_model("core", "OutboxEvent").objects.get(
        event_type="comment.deleted.v1",
        aggregate_id=comment.id,
    )
    assert event.payload["recipient_ids"] == [str(owner.id)]
    assert event.payload["reason"] == "违反评论规则"
    assert "body" not in str(event.payload).casefold()
    assert not {"client_ip", "raw_ip"} & set(event.payload)

    with pytest.raises(CommentDeletionError) as invalid_reason:
        delete_comment_as_admin(
            comment_id=_comment(thread, owner).id,
            actor_id=administrator.id,
            client_ip="198.51.100.83",
            reason="<script>",
            trace_code=new_trace_code(),
            account_policy=policy,
            media_gateway=_Media(),
        )
    assert invalid_reason.value.code == "comments.deletion_reason_invalid.v1"


def test_admin_audit_failure_rolls_back_comment_and_event(monkeypatch) -> None:
    owner = _account("cmt006-audit-owner")
    administrator = _account("cmt006-audit-admin", roles=("ADMINISTRATOR",))
    thread = _thread(owner)
    comment = _comment(thread, None, author_kind=Comment.AuthorKind.ANONYMOUS)
    policy = _Policy(
        {owner.id, administrator.id},
        {administrator.id},
    )

    def reject_audit(**kwargs):
        del kwargs
        raise AuditRejected("isolated audit failure")

    monkeypatch.setattr(
        "apps.comments.services.deletion.record_audit_entry",
        reject_audit,
    )
    with pytest.raises(AuditRejected):
        delete_comment_as_admin(
            comment_id=comment.id,
            actor_id=administrator.id,
            client_ip="198.51.100.84",
            reason="",
            trace_code=new_trace_code(),
            account_policy=policy,
            media_gateway=_Media(),
        )
    comment.refresh_from_db()
    assert comment.state == Comment.State.VISIBLE
    assert (
        not apps.get_model("core", "OutboxEvent")
        .objects.filter(aggregate_id=comment.id)
        .exists()
    )
    assert (
        not apps.get_model("operations", "AuditEntry")
        .objects.filter(target_id=comment.id)
        .exists()
    )
