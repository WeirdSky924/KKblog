from datetime import timedelta
from uuid import uuid4

import pytest
from django.apps import apps
from django.utils import timezone

from apps.core.ids import new_ulid
from apps.moderation.models import Report, ReportReason
from apps.moderation.services import (
    ReportSubmissionError,
    create_report,
    report_evidence_access,
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


class _Evidence:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = []

    def bind_evidence(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("evidence unavailable")
        return tuple(
            f"asset-{index}" for index, _ in enumerate(kwargs["evidence_refs"], 1)
        )


def _account(label: str):
    return apps.get_model("accounts", "Account").objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )


def _comment(author):
    comment_model = apps.get_model("comments", "Comment")
    thread_model = apps.get_model("comments", "DiscussionThread")
    owner = _account("cmt008-owner")
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
        body="可举报留言",
        state=comment_model.State.VISIBLE,
        visible_at=now,
        depth=0,
        reply_count=0,
        client_ip="192.0.2.80",
        created_at=now,
    )


def _create(*, actor, comment, accounts, evidence=None, **overrides):
    values = {
        "actor_id": actor.id if actor is not None else None,
        "comment_id": comment.id,
        "reason": ReportReason.SPAM,
        "description": "重复广告链接",
        "evidence_refs": (),
        "client_ip": "198.51.100.80",
        "account_policy": accounts,
        "evidence_gateway": evidence or _Evidence(),
    }
    values.update(overrides)
    return create_report(**values)


def test_report_requires_active_login_and_reportable_target() -> None:
    comment_model = apps.get_model("comments", "Comment")
    reporter = _account("cmt008-reporter")
    target_author = _account("cmt008-target")
    comment = _comment(target_author)

    with pytest.raises(ReportSubmissionError) as anonymous:
        _create(actor=None, comment=comment, accounts=_Accounts())
    assert anonymous.value.code == "moderation.login_required.v1"

    with pytest.raises(ReportSubmissionError) as inactive:
        _create(actor=reporter, comment=comment, accounts=_Accounts())
    assert inactive.value.code == "moderation.account_unavailable.v1"

    blocked_accounts = _Accounts(
        active=(reporter.id,),
        blocked=("198.51.100.80",),
    )
    with pytest.raises(ReportSubmissionError) as blocked:
        _create(actor=reporter, comment=comment, accounts=blocked_accounts)
    assert blocked.value.code == "moderation.network_restricted.v1"

    comment.state = comment_model.State.DELETED
    comment.body = ""
    comment.deleted_by_kind = comment_model.DeletedByKind.SELF
    comment.save(update_fields=("state", "body", "deleted_by_kind", "updated_at"))
    with pytest.raises(ReportSubmissionError) as deleted:
        _create(
            actor=reporter,
            comment=comment,
            accounts=_Accounts(active=(reporter.id,)),
        )
    assert deleted.value.code == "moderation.target_unavailable.v1"


def test_report_validates_reason_description_evidence_and_permanent_unique() -> None:
    reporter = _account("cmt008-reporter")
    target_author = _account("cmt008-target")
    comment = _comment(target_author)
    accounts = _Accounts(active=(reporter.id,))

    with pytest.raises(ReportSubmissionError) as invalid_reason:
        _create(actor=reporter, comment=comment, accounts=accounts, reason="HTML")
    assert invalid_reason.value.code == "moderation.reason_invalid.v1"

    with pytest.raises(ReportSubmissionError) as long_description:
        _create(
            actor=reporter,
            comment=comment,
            accounts=accounts,
            description="说" * 201,
        )
    assert long_description.value.code == "moderation.description_invalid.v1"

    with pytest.raises(ReportSubmissionError) as four_images:
        _create(
            actor=reporter,
            comment=comment,
            accounts=accounts,
            evidence_refs=("one", "two", "three", "four"),
        )
    assert four_images.value.code == "moderation.evidence_invalid.v1"

    evidence = _Evidence()
    created = _create(
        actor=reporter,
        comment=comment,
        accounts=accounts,
        evidence=evidence,
        reason=ReportReason.PRIVACY,
        description="  泄露私人信息  ",
        evidence_refs=("one", "two", "three"),
    )
    report = Report.objects.get(pk=created.report_id)
    assert report.target_comment_id == comment.id
    assert report.reporter_id == reporter.id
    assert report.reported_author_id == target_author.id
    assert report.reason == ReportReason.PRIVACY
    assert report.description == "泄露私人信息"
    assert report.state == Report.State.PENDING
    assert created.evidence_count == 3
    assert evidence.calls[0]["report_id"] == report.id

    report.state = Report.State.CLOSED
    report.save(update_fields=("state", "updated_at"))
    with pytest.raises(ReportSubmissionError) as duplicate:
        _create(actor=reporter, comment=comment, accounts=accounts)
    assert duplicate.value.code == "moderation.report_duplicate.v1"


def test_evidence_binding_rolls_back_report_and_private_access_is_rechecked() -> None:
    reporter = _account("cmt008-reporter")
    target_author = _account("cmt008-target")
    administrator = _account("cmt008-admin")
    other = _account("cmt008-other")
    comment = _comment(target_author)
    accounts = _Accounts(
        active=(reporter.id, target_author.id, administrator.id, other.id),
        administrators=(administrator.id,),
    )

    with pytest.raises(RuntimeError, match="evidence unavailable"):
        _create(
            actor=reporter,
            comment=comment,
            accounts=accounts,
            evidence=_Evidence(fail=True),
            evidence_refs=("one",),
        )
    assert Report.objects.count() == 0

    created = _create(
        actor=reporter,
        comment=comment,
        accounts=accounts,
        evidence_refs=("one",),
    )
    reporter_access = report_evidence_access(
        actor_id=reporter.id,
        report_id=created.report_id,
        account_policy=accounts,
    )
    admin_access = report_evidence_access(
        actor_id=administrator.id,
        report_id=created.report_id,
        account_policy=accounts,
    )
    target_access = report_evidence_access(
        actor_id=target_author.id,
        report_id=created.report_id,
        account_policy=accounts,
    )
    other_access = report_evidence_access(
        actor_id=other.id,
        report_id=created.report_id,
        account_policy=accounts,
    )
    assert (
        reporter_access.exists,
        reporter_access.can_bind,
        reporter_access.can_read,
    ) == (True, True, True)
    assert (admin_access.exists, admin_access.can_bind, admin_access.can_read) == (
        True,
        False,
        True,
    )
    assert (
        target_access.exists,
        target_access.can_bind,
        target_access.can_read,
    ) == (True, False, False)
    assert other_access == target_access
