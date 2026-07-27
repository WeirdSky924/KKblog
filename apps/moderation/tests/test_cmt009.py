from datetime import timedelta
from uuid import uuid4

import pytest
from django.apps import apps
from django.utils import timezone

from apps.comments.public import delete_comment_for_report
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.moderation.models import Report, ReportRecoverySnapshot
from apps.moderation.services import (
    ReportReviewError,
    ReportReviewOutcome,
    report_recovery_snapshot_access,
    review_report,
)

pytestmark = pytest.mark.django_db(transaction=True)


class _Accounts:
    def __init__(self, *, active=(), administrators=(), blocked=()):
        self.active = set(active)
        self.administrators = set(administrators)
        self.blocked = set(blocked)

    def is_active_account(self, account_id):
        return account_id in self.active

    def is_administrator(self, account_id):
        return account_id in self.administrators

    def is_ip_blocked(self, client_ip):
        return client_ip in self.blocked


class _Media:
    def __init__(self, asset_ids=()):
        self.asset_ids = tuple(asset_ids)
        self.released = []

    def release_images(self, comment_id):
        self.released.append(comment_id)
        return self.asset_ids


def _account(label: str, *, roles=()):
    account = apps.get_model("accounts", "Account").objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    role_model = apps.get_model("accounts", "RoleAssignment")
    for role in roles:
        role_model.objects.create(account=account, role=role)
    return account


def _comment(author):
    comment_model = apps.get_model("comments", "Comment")
    thread_model = apps.get_model("comments", "DiscussionThread")
    owner = _account("cmt009-owner")
    thread = thread_model.objects.create(
        target_type=thread_model.TargetType.GUESTBOOK,
        target_id="site",
        owner=owner,
    )
    now = timezone.now() - timedelta(minutes=20)
    identity = new_ulid()
    return comment_model.objects.create(
        id=identity,
        thread=thread,
        parent=None,
        root_id=identity,
        author=author,
        author_kind=comment_model.AuthorKind.ACCOUNT,
        body="需要私有恢复的评论正文",
        state=comment_model.State.VISIBLE,
        visible_at=now,
        depth=0,
        reply_count=0,
        client_ip="192.0.2.90",
        created_at=now,
    )


def _report(reporter, comment):
    return Report.objects.create(
        target_comment_id=comment.id,
        reporter_id=reporter.id,
        reported_author_id=comment.author_id,
        reason="HARASSMENT",
        description="只应留在举报记录中的描述",
    )


def _review(admin, report, outcome, **overrides):
    values = {
        "actor_id": admin.id,
        "report_id": report.id,
        "outcome": outcome,
        "decision_reason": "已核对上下文",
        "client_ip": "198.51.100.90",
        "trace_code": new_trace_code(),
    }
    values.update(overrides)
    return review_report(**values)


def test_upheld_review_deletes_comment_and_keeps_private_snapshot() -> None:
    admin = _account("cmt009-admin", roles=("ADMINISTRATOR",))
    reporter = _account("cmt009-reporter")
    target = _account("cmt009-target")
    comment = _comment(target)
    report = _report(reporter, comment)

    result = _review(admin, report, ReportReviewOutcome.UPHELD)

    report.refresh_from_db()
    comment.refresh_from_db()
    snapshot = ReportRecoverySnapshot.objects.get(report=report)
    assert (result.state, report.state) == ("UPHELD", Report.State.UPHELD)
    assert (comment.state, comment.body, comment.deleted_by_kind) == (
        "DELETED",
        "",
        "REPORT",
    )
    assert (snapshot.comment_id, snapshot.body, snapshot.previous_state) == (
        comment.id,
        "需要私有恢复的评论正文",
        "VISIBLE",
    )
    assert snapshot.image_count == 0

    audit = apps.get_model("operations", "AuditEntry").objects.get(
        action="moderation.report.review"
    )
    assert audit.before_safe == {"state": "PENDING"}
    assert audit.after_safe == {
        "comment_changed": True,
        "image_count": 0,
        "outcome": "UPHELD",
        "reason_provided": True,
        "snapshot_created": True,
        "state": "UPHELD",
    }
    event = apps.get_model("core", "OutboxEvent").objects.get(
        event_type="report.reviewed.v1"
    )
    assert event.aggregate_id == report.id
    assert event.payload == {
        "decision_reason": "已核对上下文",
        "outcome": "UPHELD",
        "recipient_ids": [str(reporter.id), str(target.id)],
        "target_comment_id": comment.id,
    }
    assert report.description not in str(event.payload)
    assert snapshot.body not in str(event.payload)

    assert report_recovery_snapshot_access(
        actor_id=admin.id,
        report_id=report.id,
    ).can_read
    assert not report_recovery_snapshot_access(
        actor_id=reporter.id,
        report_id=report.id,
    ).can_read
    assert not report_recovery_snapshot_access(
        actor_id=target.id,
        report_id=report.id,
    ).can_read

    with pytest.raises(ReportReviewError) as duplicate:
        _review(admin, report, ReportReviewOutcome.REJECTED)
    assert duplicate.value.code == "moderation.report_state_conflict.v1"
    assert apps.get_model("core", "OutboxEvent").objects.count() == 1


def test_rejected_review_keeps_comment_and_notifies_only_reporter() -> None:
    admin = _account("cmt009-admin", roles=("ADMINISTRATOR",))
    reporter = _account("cmt009-reporter")
    target = _account("cmt009-target")
    comment = _comment(target)
    report = _report(reporter, comment)

    result = _review(admin, report, ReportReviewOutcome.REJECTED)

    comment.refresh_from_db()
    assert result.state == Report.State.REJECTED
    assert (comment.state, comment.body) == (
        "VISIBLE",
        "需要私有恢复的评论正文",
    )
    assert not ReportRecoverySnapshot.objects.filter(report=report).exists()
    event = apps.get_model("core", "OutboxEvent").objects.get()
    assert event.payload["recipient_ids"] == [str(reporter.id)]
    assert event.payload["outcome"] == "REJECTED"


def test_review_rechecks_admin_account_network_and_input() -> None:
    admin = _account("cmt009-admin", roles=("ADMINISTRATOR",))
    member = _account("cmt009-member")
    reporter = _account("cmt009-reporter")
    target = _account("cmt009-target")
    report = _report(reporter, _comment(target))

    with pytest.raises(ReportReviewError) as denied:
        _review(member, report, ReportReviewOutcome.REJECTED)
    assert denied.value.code == "moderation.review_forbidden.v1"

    accounts = _Accounts(
        active=(admin.id,),
        administrators=(admin.id,),
        blocked=("198.51.100.90",),
    )
    with pytest.raises(ReportReviewError) as blocked:
        _review(
            admin,
            report,
            ReportReviewOutcome.REJECTED,
            account_policy=accounts,
        )
    assert blocked.value.code == "moderation.network_restricted.v1"

    with pytest.raises(ReportReviewError) as unsafe_reason:
        _review(
            admin,
            report,
            ReportReviewOutcome.REJECTED,
            decision_reason="https://unsafe.example",
        )
    assert unsafe_reason.value.code == "moderation.decision_reason_invalid.v1"
    report.refresh_from_db()
    assert report.state == Report.State.PENDING


def test_audit_failure_rolls_back_comment_report_snapshot_and_event(
    monkeypatch,
) -> None:
    admin = _account("cmt009-admin", roles=("ADMINISTRATOR",))
    reporter = _account("cmt009-reporter")
    target = _account("cmt009-target")
    comment = _comment(target)
    report = _report(reporter, comment)

    from apps.moderation.services import review as review_service

    monkeypatch.setattr(
        review_service,
        "record_audit_entry",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("audit unavailable")),
    )
    with pytest.raises(RuntimeError, match="audit unavailable"):
        _review(admin, report, ReportReviewOutcome.UPHELD)

    report.refresh_from_db()
    comment.refresh_from_db()
    assert report.state == Report.State.PENDING
    assert (comment.state, comment.body, comment.deleted_by_kind) == (
        "VISIBLE",
        "需要私有恢复的评论正文",
        None,
    )
    assert ReportRecoverySnapshot.objects.count() == 0
    assert apps.get_model("core", "OutboxEvent").objects.count() == 0
    assert apps.get_model("operations", "AuditEntry").objects.count() == 0


def test_comment_report_deletion_port_returns_safe_snapshot_and_releases_images() -> (
    None
):
    admin = _account("cmt009-admin", roles=("ADMINISTRATOR",))
    target = _account("cmt009-target")
    comment = _comment(target)
    assets = (new_ulid(), new_ulid())
    media = _Media(assets)

    result = delete_comment_for_report(
        comment_id=comment.id,
        actor_id=admin.id,
        client_ip="198.51.100.91",
        media_gateway=media,
    )

    assert result.changed is True
    assert result.body == "需要私有恢复的评论正文"
    assert result.previous_state == "VISIBLE"
    assert result.asset_ids == assets
    assert result.reported_author_id == target.id
    assert media.released == [comment.id]
    comment.refresh_from_db()
    assert (comment.state, comment.body, comment.deleted_by_kind) == (
        "DELETED",
        "",
        "REPORT",
    )
