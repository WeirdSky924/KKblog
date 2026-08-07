from datetime import timedelta
from uuid import uuid4

import pytest
from django.apps import apps
from django.utils import timezone

from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.moderation.models import Report, ReportAppeal, ReportRecoverySnapshot
from apps.moderation.services import (
    ReportAppealError,
    ReportFinalReviewOutcome,
    ReportReviewOutcome,
    create_report_appeal,
    finalize_report_appeal,
    report_appeal_evidence_access,
    review_report,
)

pytestmark = pytest.mark.django_db(transaction=True)


class _Accounts:
    def __init__(self, *active, administrators=()):
        self.active = set(active)
        self.administrators = set(administrators)

    def is_active_account(self, account_id):
        return account_id in self.active

    def is_administrator(self, account_id):
        return account_id in self.administrators

    def is_ip_blocked(self, _client_ip):
        return False


class _Evidence:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = []

    def bind_evidence(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("appeal evidence unavailable")
        return tuple(new_ulid() for _ in kwargs["evidence_refs"])


def _account(label):
    return apps.get_model("accounts", "Account").objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )


def _comment(author):
    owner = _account("cmt010-owner")
    thread_model = apps.get_model("comments", "DiscussionThread")
    comment_model = apps.get_model("comments", "Comment")
    thread = thread_model.objects.create(
        target_type="GUESTBOOK",
        target_id="site",
        owner=owner,
    )
    identity = new_ulid()
    now = timezone.now() - timedelta(minutes=20)
    return comment_model.objects.create(
        id=identity,
        thread=thread,
        parent=None,
        root_id=identity,
        author=author,
        author_kind="ACCOUNT",
        body="可申诉恢复的正文",
        state="VISIBLE",
        visible_at=now,
        depth=0,
        reply_count=0,
        client_ip="192.0.2.120",
        created_at=now,
    )


def _initial_review(*, admin, reporter, target, outcome):
    comment = _comment(target)
    report = Report.objects.create(
        target_comment_id=comment.id,
        reporter_id=reporter.id,
        reported_author_id=target.id,
        reason="SPAM",
        description="初次举报私有说明",
    )
    accounts = _Accounts(
        admin.id,
        reporter.id,
        target.id,
        administrators=(admin.id,),
    )
    review_report(
        actor_id=admin.id,
        report_id=report.id,
        outcome=outcome,
        decision_reason="初审说明",
        client_ip="198.51.100.120",
        trace_code=new_trace_code(),
        account_policy=accounts,
    )
    return report, comment, accounts


def _appeal(*, actor, report, accounts, evidence=None, **overrides):
    values = {
        "actor_id": actor.id,
        "report_id": report.id,
        "statement": "补充申诉说明",
        "evidence_refs": (),
        "client_ip": "198.51.100.121",
        "account_policy": accounts,
        "evidence_gateway": evidence or _Evidence(),
    }
    values.update(overrides)
    return create_report_appeal(**values)


def _finalize(*, admin, report, accounts, outcome):
    return finalize_report_appeal(
        actor_id=admin.id,
        report_id=report.id,
        outcome=outcome,
        decision_reason="复审核对完成",
        client_ip="198.51.100.122",
        trace_code=new_trace_code(),
        account_policy=accounts,
    )


def test_appeal_eligibility_is_outcome_specific_once_and_has_no_deadline() -> None:
    admin = _account("cmt010-admin")
    reporter = _account("cmt010-reporter")
    target = _account("cmt010-target")
    rejected, _, accounts = _initial_review(
        admin=admin,
        reporter=reporter,
        target=target,
        outcome=ReportReviewOutcome.REJECTED,
    )
    rejected.reviewed_at = timezone.now() - timedelta(days=3650)
    rejected.save(update_fields=("reviewed_at", "updated_at"))

    with pytest.raises(ReportAppealError) as wrong_party:
        _appeal(actor=target, report=rejected, accounts=accounts)
    assert wrong_party.value.code == "moderation.appeal_forbidden.v1"

    evidence = _Evidence()
    result = _appeal(
        actor=reporter,
        report=rejected,
        accounts=accounts,
        evidence=evidence,
        evidence_refs=("one", "two", "three"),
    )
    rejected.refresh_from_db()
    appeal = ReportAppeal.objects.get(report=rejected)
    assert (result.state, rejected.state, appeal.basis_outcome) == (
        "APPEAL_PENDING",
        "APPEAL_PENDING",
        "REJECTED",
    )
    assert len(evidence.calls[0]["evidence_refs"]) == 3
    reporter_access = report_appeal_evidence_access(
        actor_id=reporter.id,
        appeal_id=appeal.id,
        account_policy=accounts,
    )
    assert reporter_access.can_read
    assert not reporter_access.can_bind
    assert report_appeal_evidence_access(
        actor_id=admin.id,
        appeal_id=appeal.id,
        account_policy=accounts,
    ).can_read
    assert not report_appeal_evidence_access(
        actor_id=target.id,
        appeal_id=appeal.id,
        account_policy=accounts,
    ).can_read
    with pytest.raises(ReportAppealError) as duplicate:
        _appeal(actor=reporter, report=rejected, accounts=accounts)
    assert duplicate.value.code == "moderation.appeal_state_conflict.v1"


def test_final_rejected_restores_upheld_comment_and_destroys_snapshot() -> None:
    admin = _account("cmt010-admin")
    reporter = _account("cmt010-reporter")
    target = _account("cmt010-target")
    report, comment, accounts = _initial_review(
        admin=admin,
        reporter=reporter,
        target=target,
        outcome=ReportReviewOutcome.UPHELD,
    )
    with pytest.raises(ReportAppealError) as wrong_party:
        _appeal(actor=reporter, report=report, accounts=accounts)
    assert wrong_party.value.code == "moderation.appeal_forbidden.v1"
    _appeal(actor=target, report=report, accounts=accounts)

    result = _finalize(
        admin=admin,
        report=report,
        accounts=accounts,
        outcome=ReportFinalReviewOutcome.REJECTED,
    )

    report.refresh_from_db()
    comment.refresh_from_db()
    appeal = ReportAppeal.objects.get(report=report)
    assert (result.state, report.state, appeal.state) == (
        "FINAL_REJECTED",
        "FINAL_REJECTED",
        "FINAL_REJECTED",
    )
    assert (comment.state, comment.body, comment.deleted_by_kind) == (
        "VISIBLE",
        "可申诉恢复的正文",
        None,
    )
    assert not ReportRecoverySnapshot.objects.filter(report=report).exists()
    event = apps.get_model("core", "OutboxEvent").objects.get(
        event_type="report.finalized.v2"
    )
    assert event.payload["reason"] == "SPAM"
    assert event.payload["description"] == "初次举报私有说明"
    assert event.payload["basis_outcome"] == "UPHELD"
    assert event.payload["recovery_status"] == "RESTORED"
    assert event.payload["recipient_ids"] == [str(reporter.id), str(target.id)]
    assert appeal.statement not in str(event.payload)
    with pytest.raises(ReportAppealError) as duplicate_final:
        _finalize(
            admin=admin,
            report=report,
            accounts=accounts,
            outcome=ReportFinalReviewOutcome.UPHELD,
        )
    assert duplicate_final.value.code == "moderation.final_review_state_conflict.v1"
    assert (
        apps.get_model("core", "OutboxEvent")
        .objects.filter(event_type="report.finalized.v2")
        .count()
        == 1
    )


def test_final_upheld_after_rejected_review_executes_deletion() -> None:
    admin = _account("cmt010-admin")
    reporter = _account("cmt010-reporter")
    target = _account("cmt010-target")
    report, comment, accounts = _initial_review(
        admin=admin,
        reporter=reporter,
        target=target,
        outcome=ReportReviewOutcome.REJECTED,
    )
    _appeal(actor=reporter, report=report, accounts=accounts)

    _finalize(
        admin=admin,
        report=report,
        accounts=accounts,
        outcome=ReportFinalReviewOutcome.UPHELD,
    )

    report.refresh_from_db()
    comment.refresh_from_db()
    assert report.state == "FINAL_UPHELD"
    assert (comment.state, comment.body, comment.deleted_by_kind) == (
        "DELETED",
        "",
        "REPORT",
    )
    assert not ReportRecoverySnapshot.objects.filter(report=report).exists()


def test_recovery_failure_finalizes_case_but_keeps_private_snapshot() -> None:
    admin = _account("cmt010-admin")
    reporter = _account("cmt010-reporter")
    target = _account("cmt010-target")
    report, comment, accounts = _initial_review(
        admin=admin,
        reporter=reporter,
        target=target,
        outcome=ReportReviewOutcome.UPHELD,
    )
    _appeal(actor=target, report=report, accounts=accounts)
    comment.delete()

    result = _finalize(
        admin=admin,
        report=report,
        accounts=accounts,
        outcome=ReportFinalReviewOutcome.REJECTED,
    )

    report.refresh_from_db()
    appeal = ReportAppeal.objects.get(report=report)
    assert (result.state, result.recovery_status) == ("FINAL_REJECTED", "FAILED")
    assert report.state == "FINAL_REJECTED"
    assert appeal.recovery_error_code == "comments.report_recovery_target_missing.v1"
    assert ReportRecoverySnapshot.objects.filter(report=report).exists()
    event = apps.get_model("core", "OutboxEvent").objects.get(
        event_type="report.finalized.v2"
    )
    assert event.payload["recovery_status"] == "FAILED"
    assert appeal.recovery_error_code not in str(event.payload)


def test_final_audit_failure_rolls_back_restoration_and_case(monkeypatch) -> None:
    admin = _account("cmt010-admin")
    reporter = _account("cmt010-reporter")
    target = _account("cmt010-target")
    report, comment, accounts = _initial_review(
        admin=admin,
        reporter=reporter,
        target=target,
        outcome=ReportReviewOutcome.UPHELD,
    )
    _appeal(actor=target, report=report, accounts=accounts)

    from apps.moderation.services import appeals as appeal_service

    monkeypatch.setattr(
        appeal_service,
        "record_audit_entry",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("audit unavailable")),
    )
    with pytest.raises(RuntimeError, match="audit unavailable"):
        _finalize(
            admin=admin,
            report=report,
            accounts=accounts,
            outcome=ReportFinalReviewOutcome.REJECTED,
        )

    report.refresh_from_db()
    comment.refresh_from_db()
    appeal = ReportAppeal.objects.get(report=report)
    assert (report.state, appeal.state) == ("APPEAL_PENDING", "PENDING")
    assert (comment.state, comment.body, comment.deleted_by_kind) == (
        "DELETED",
        "",
        "REPORT",
    )
    assert ReportRecoverySnapshot.objects.filter(report=report).exists()
    assert (
        not apps.get_model("core", "OutboxEvent")
        .objects.filter(event_type="report.finalized.v2")
        .exists()
    )


def test_appeal_input_binding_and_final_permissions_fail_closed() -> None:
    admin = _account("cmt010-admin")
    reporter = _account("cmt010-reporter")
    target = _account("cmt010-target")
    report, _, accounts = _initial_review(
        admin=admin,
        reporter=reporter,
        target=target,
        outcome=ReportReviewOutcome.REJECTED,
    )

    with pytest.raises(ReportAppealError) as long_text:
        _appeal(
            actor=reporter,
            report=report,
            accounts=accounts,
            statement="申" * 201,
        )
    assert long_text.value.code == "moderation.appeal_text_invalid.v1"
    with pytest.raises(ReportAppealError) as four_images:
        _appeal(
            actor=reporter,
            report=report,
            accounts=accounts,
            evidence_refs=("one", "two", "three", "four"),
        )
    assert four_images.value.code == "moderation.appeal_evidence_invalid.v1"
    with pytest.raises(RuntimeError, match="appeal evidence unavailable"):
        _appeal(
            actor=reporter,
            report=report,
            accounts=accounts,
            evidence=_Evidence(fail=True),
            evidence_refs=("one",),
        )
    report.refresh_from_db()
    assert report.state == "REJECTED"
    assert not ReportAppeal.objects.filter(report=report).exists()

    _appeal(actor=reporter, report=report, accounts=accounts)
    denied_accounts = _Accounts(admin.id, reporter.id, target.id)
    with pytest.raises(ReportAppealError) as denied:
        _finalize(
            admin=admin,
            report=report,
            accounts=denied_accounts,
            outcome=ReportFinalReviewOutcome.REJECTED,
        )
    assert denied.value.code == "moderation.final_review_forbidden.v1"
    report.refresh_from_db()
    assert report.state == "APPEAL_PENDING"
