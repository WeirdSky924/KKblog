import json
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import uuid4

import pytest
from django.apps import apps
from PIL import Image

from apps.content.public import (
    ArticleDeletionError,
    ArticleNotFound,
    article_for_author,
    article_for_reader,
    open_edit_session,
    purge_deleted_article,
    restore_deleted_article,
)
from apps.content.services.editing import EditTokenError
from apps.core.events import ConsumerOutcome, EventEnvelope
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock
from apps.moderation.models import (
    ArticleAppeal,
    ArticleModerationCase,
    DeletedAccountIdentity,
    Report,
    ReportAppeal,
    ReportRecoverySnapshot,
)
from apps.moderation.public import consume_account_deleted
from apps.moderation.services import (
    ArticleAction,
    ArticleAppealReviewOutcome,
    ArticleCaseError,
    appeal_article_action,
    article_appeal_evidence_access,
    create_article_moderation_case,
    restore_article_moderation_case,
    review_article_appeal,
    stage_article_appeal_evidence,
)
from config.comment_integrations import configure_comment_integrations
from config.moderation_integrations import configure_moderation_integrations

Article = apps.get_model("content", "Article")
ArticleRevision = apps.get_model("content", "ArticleRevision")
ArticleTombstone = apps.get_model("content", "ArticleTombstone")

pytestmark = pytest.mark.django_db(transaction=True)


class _Evidence:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls = []

    def bind_evidence(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("article appeal evidence unavailable")
        return tuple(new_ulid() for _ in kwargs["evidence_refs"])


@pytest.fixture(autouse=True)
def _configure_integrations():
    configure_comment_integrations()
    configure_moderation_integrations()


def _account(label: str, *, author: bool = False, administrator: bool = False):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    if author or administrator:
        role_model.objects.create(account=account, role="AUTHOR")
    if administrator:
        role_model.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _article(author, *, published: bool = True, visibility: str = "PUBLIC"):
    article = Article.objects.create(author=author, row_version=1)
    revision = ArticleRevision.objects.create(
        article=article,
        sequence=1,
        content_format="MARKDOWN",
        title="需要审核的文章",
        body_markdown="不应进入案件或事件的正文",
        summary_mode="AUTO",
        visibility=visibility,
        created_by=author,
    )
    values = {"working_revision_id": revision.id}
    if published:
        values.update(
            publication_state="PUBLISHED",
            published_revision_id=revision.id,
            published_at=datetime(2026, 7, 25, 2, 0, tzinfo=UTC),
            last_published_at=datetime(2026, 7, 25, 2, 0, tzinfo=UTC),
        )
    Article.objects.filter(pk=article.id).update(**values)
    article.refresh_from_db()
    return article, revision


def _context(*, clock=None):
    values = {
        "client_ip": "198.51.100.211",
        "trace_code": new_trace_code(),
    }
    if clock is not None:
        values["clock"] = clock
    return values


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (24, 16), "#3b82a0").save(output, format="PNG")
    return output.getvalue()


def _create_case(admin, article, action, *, reason="审核原因"):
    return create_article_moderation_case(
        actor_id=admin.id,
        article_id=article.id,
        action=action,
        reason=reason,
        **_context(),
    )


def test_hide_is_published_only_masks_readers_and_keeps_article_exact() -> None:
    admin = _account("cmt011-admin", administrator=True)
    author = _account("cmt011-author", author=True)
    reader = _account("cmt011-reader")
    article, revision = _article(author, visibility="AUTHENTICATED")
    before = Article.objects.filter(pk=article.id).values().get()

    result = _create_case(admin, article, ArticleAction.HIDE)

    case = ArticleModerationCase.objects.get(pk=result.case_id)
    after = Article.objects.filter(pk=article.id).values().get()
    assert before == after
    assert (case.action, case.state, case.author_id) == (
        "HIDE",
        "ACTIVE",
        author.id,
    )
    assert case.pre_action_snapshot["published_revision_id"] == revision.id
    assert case.pre_action_snapshot["visibility"] == "AUTHENTICATED"
    assert "body" not in str(case.pre_action_snapshot).casefold()
    with pytest.raises(ArticleNotFound):
        article_for_reader(actor_id=reader.id, article_id=article.id)
    author_view = article_for_author(actor_id=author.id, article_id=article.id)
    assert author_view.admin_read_only is False and author_view.can_edit is False
    with pytest.raises(EditTokenError):
        open_edit_session(actor_id=author.id, article_id=article.id)
    with pytest.raises(EditTokenError):
        open_edit_session(actor_id=admin.id, article_id=article.id)

    draft, _ = _article(author, published=False)
    with pytest.raises(ArticleCaseError) as draft_hide:
        _create_case(admin, draft, ArticleAction.HIDE)
    assert draft_hide.value.code == "moderation.article_hide_not_allowed.v1"
    with pytest.raises(ArticleCaseError) as self_action:
        own, _ = _article(admin)
        _create_case(admin, own, ArticleAction.HIDE)
    assert self_action.value.code == "moderation.article_action_not_allowed.v1"
    with pytest.raises(ArticleCaseError) as forged_action:
        _create_case(author, article, ArticleAction.DELETE)
    assert forged_action.value.code == "moderation.article_action_not_allowed.v1"

    restored = restore_article_moderation_case(
        actor_id=admin.id,
        case_id=case.id,
        **_context(),
    )
    case.refresh_from_db()
    assert (restored.state, restored.recovery_status, case.state) == (
        "RESTORED",
        "RESTORED",
        "RESTORED",
    )
    visible = article_for_reader(actor_id=reader.id, article_id=article.id)
    assert (visible.revision_id, visible.visibility) == (revision.id, "AUTHENTICATED")
    audit = apps.get_model("operations", "AuditEntry")
    assert list(
        audit.objects.filter(target_id=article.id)
        .order_by("created_at", "id")
        .values_list("action", flat=True)
    ) == ["moderation.article.action", "moderation.article.restore"]


def test_delete_delegates_to_content_and_audit_failure_rolls_back(monkeypatch) -> None:
    now = datetime(2026, 7, 25, 3, 0, tzinfo=UTC)
    admin = _account("cmt011-admin", administrator=True)
    author = _account("cmt011-author", author=True)
    article, revision = _article(author, visibility="PRIVATE")

    result = create_article_moderation_case(
        actor_id=admin.id,
        article_id=article.id,
        action=ArticleAction.DELETE,
        reason="管理员删除说明",
        **_context(clock=FrozenClock(now)),
    )

    article.refresh_from_db()
    case = ArticleModerationCase.objects.get(pk=result.case_id)
    tombstone = ArticleTombstone.objects.get(article_id=article.id)
    assert article.deleted_at == now
    assert tombstone.administrative is True
    assert case.pre_action_snapshot["working_revision_id"] == revision.id
    assert result.article_changed is True
    assert (
        apps.get_model("core", "OutboxEvent")
        .objects.filter(
            aggregate_id=article.id,
            event_type="article.deleted.v1",
        )
        .exists()
    )

    rollback_article, _ = _article(author)
    from apps.moderation.services import article_cases

    monkeypatch.setattr(
        article_cases,
        "record_audit_entry",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("audit unavailable")),
    )
    with pytest.raises(RuntimeError, match="audit unavailable"):
        _create_case(admin, rollback_article, ArticleAction.DELETE)
    rollback_article.refresh_from_db()
    assert rollback_article.deleted_at is None
    assert not ArticleTombstone.objects.filter(article_id=rollback_article.id).exists()
    assert not ArticleModerationCase.objects.filter(
        article_id=rollback_article.id
    ).exists()

    appeal = appeal_article_action(
        actor_id=author.id,
        case_id=case.id,
        statement="请求恢复删除前状态",
        evidence_refs=(),
        client_ip="198.51.100.212",
        evidence_gateway=_Evidence(),
    )
    final = review_article_appeal(
        actor_id=admin.id,
        appeal_id=appeal.appeal_id,
        outcome=ArticleAppealReviewOutcome.GRANTED,
        decision_reason="申诉成立",
        **_context(clock=FrozenClock(now + timedelta(days=1))),
    )
    article.refresh_from_db()
    case.refresh_from_db()
    stored_appeal = ArticleAppeal.objects.get(pk=appeal.appeal_id)
    assert (final.state, final.recovery_status) == ("FINAL_REJECTED", "RESTORED")
    assert (case.state, stored_appeal.state) == (
        "FINAL_REJECTED",
        "FINAL_REJECTED",
    )
    assert article.deleted_at is None
    assert article.publication_state == "PUBLISHED"
    assert article.working_revision_id == revision.id
    assert article.published_revision_id == revision.id
    assert not ArticleTombstone.objects.filter(article_id=article.id).exists()


def test_admin_delete_and_restore_cannot_bypass_moderation_case() -> None:
    now = datetime(2026, 7, 25, 3, 30, tzinfo=UTC)
    admin = _account("cmt011-admin", administrator=True)
    author = _account("cmt011-author", author=True)
    article, _ = _article(author)
    case_result = create_article_moderation_case(
        actor_id=admin.id,
        article_id=article.id,
        action=ArticleAction.DELETE,
        reason="必须经文章案件恢复",
        **_context(clock=FrozenClock(now)),
    )
    deleted = Article.objects.get(pk=article.id)

    with pytest.raises(ArticleDeletionError) as direct_restore:
        restore_deleted_article(
            actor_id=admin.id,
            article_id=article.id,
            expected_row_version=deleted.row_version,
            **_context(clock=FrozenClock(now + timedelta(days=1))),
        )
    assert direct_restore.value.code == "content.article_restore_not_allowed.v1"
    deleted.refresh_from_db()
    case = ArticleModerationCase.objects.get(pk=case_result.case_id)
    assert deleted.deleted_at is not None and case.state == "ACTIVE"

    restored = restore_article_moderation_case(
        actor_id=admin.id,
        case_id=case.id,
        **_context(clock=FrozenClock(now + timedelta(days=1))),
    )
    deleted.refresh_from_db()
    case.refresh_from_db()
    assert (restored.state, deleted.deleted_at, case.state) == (
        "RESTORED",
        None,
        "RESTORED",
    )


def test_article_appeal_is_once_private_and_final_rejection_keeps_hide() -> None:
    admin = _account("cmt011-admin", administrator=True)
    author = _account("cmt011-author", author=True)
    other = _account("cmt011-other", author=True)
    reader = _account("cmt011-reader")
    article, _ = _article(author)
    case_result = _create_case(admin, article, ArticleAction.HIDE)

    with pytest.raises(ArticleCaseError) as wrong_party:
        appeal_article_action(
            actor_id=other.id,
            case_id=case_result.case_id,
            statement="伪造申诉",
            evidence_refs=(),
            client_ip="198.51.100.213",
            evidence_gateway=_Evidence(),
        )
    assert wrong_party.value.code == "moderation.article_appeal_forbidden.v1"
    with pytest.raises(ArticleCaseError) as long_text:
        appeal_article_action(
            actor_id=author.id,
            case_id=case_result.case_id,
            statement="申" * 201,
            evidence_refs=(),
            client_ip="198.51.100.213",
            evidence_gateway=_Evidence(),
        )
    assert long_text.value.code == "moderation.article_appeal_text_invalid.v1"
    with pytest.raises(ArticleCaseError) as four_images:
        appeal_article_action(
            actor_id=author.id,
            case_id=case_result.case_id,
            statement="证据过多",
            evidence_refs=("1", "2", "3", "4"),
            client_ip="198.51.100.213",
            evidence_gateway=_Evidence(),
        )
    assert four_images.value.code == "moderation.article_appeal_evidence_invalid.v1"

    evidence = _Evidence()
    appeal = appeal_article_action(
        actor_id=author.id,
        case_id=case_result.case_id,
        statement="请重新审核",
        evidence_refs=("1", "2", "3"),
        client_ip="198.51.100.213",
        evidence_gateway=evidence,
    )
    assert len(evidence.calls[0]["evidence_refs"]) == 3
    assert article_appeal_evidence_access(
        actor_id=author.id, appeal_id=appeal.appeal_id
    ).can_read
    assert article_appeal_evidence_access(
        actor_id=admin.id, appeal_id=appeal.appeal_id
    ).can_read
    assert not article_appeal_evidence_access(
        actor_id=reader.id, appeal_id=appeal.appeal_id
    ).can_read
    with pytest.raises(ArticleCaseError) as duplicate:
        appeal_article_action(
            actor_id=author.id,
            case_id=case_result.case_id,
            statement="重复申诉",
            evidence_refs=(),
            client_ip="198.51.100.213",
            evidence_gateway=_Evidence(),
        )
    assert duplicate.value.code == "moderation.article_appeal_state_conflict.v1"

    final = review_article_appeal(
        actor_id=admin.id,
        appeal_id=appeal.appeal_id,
        outcome=ArticleAppealReviewOutcome.REJECTED,
        decision_reason="维持隐藏",
        **_context(),
    )
    assert (final.state, final.recovery_status) == (
        "FINAL_UPHELD",
        "NOT_REQUIRED",
    )
    with pytest.raises(ArticleNotFound):
        article_for_reader(actor_id=reader.id, article_id=article.id)
    with pytest.raises(ArticleCaseError) as duplicate_review:
        review_article_appeal(
            actor_id=admin.id,
            appeal_id=appeal.appeal_id,
            outcome=ArticleAppealReviewOutcome.GRANTED,
            decision_reason="重复复审",
            **_context(),
        )
    assert duplicate_review.value.code == (
        "moderation.article_final_review_state_conflict.v1"
    )


def test_article_appeal_real_evidence_is_private(
    isolated_media_root,
) -> None:
    admin = _account("cmt011-admin", administrator=True)
    author = _account("cmt011-author", author=True)
    other = _account("cmt011-other")
    article, _ = _article(author)
    case = _create_case(admin, article, ArticleAction.HIDE)

    upload = stage_article_appeal_evidence(
        actor_id=author.id,
        case_id=case.case_id,
        client_ip="198.51.100.216",
        original_name="appeal.png",
        declared_content_type="image/png",
        chunks=[_png()],
    )
    appeal = appeal_article_action(
        actor_id=author.id,
        case_id=case.case_id,
        statement="附图说明",
        evidence_refs=(upload.evidence_ref,),
        client_ip="198.51.100.216",
    )

    binding = apps.get_model("media", "MediaBinding").objects.get(
        asset_id=upload.asset_id
    )
    assert (binding.target_type, binding.target_id, binding.slot) == (
        "article_appeal",
        appeal.appeal_id,
        "evidence-1",
    )
    asset = apps.get_model("media", "MediaAsset").objects.get(pk=upload.asset_id)
    assert (isolated_media_root / asset.storage_key).exists()
    assert article_appeal_evidence_access(
        actor_id=author.id,
        appeal_id=appeal.appeal_id,
    ).can_read
    assert article_appeal_evidence_access(
        actor_id=admin.id,
        appeal_id=appeal.appeal_id,
    ).can_read
    for actor_id in (other.id, None):
        assert not article_appeal_evidence_access(
            actor_id=actor_id,
            appeal_id=appeal.appeal_id,
        ).can_read
    review_article_appeal(
        actor_id=admin.id,
        appeal_id=appeal.appeal_id,
        outcome=ArticleAppealReviewOutcome.REJECTED,
        decision_reason="维持管理动作",
        **_context(),
    )
    case_record = ArticleModerationCase.objects.get(pk=case.case_id)
    audits = list(
        apps.get_model("operations", "AuditEntry")
        .objects.filter(target_id=article.id)
        .values("action", "before_safe", "after_safe", "summary")
    )
    events = list(
        apps.get_model("core", "OutboxEvent")
        .objects.filter(aggregate_id=article.id)
        .values("event_type", "payload")
    )
    serialized = json.dumps(
        {
            "snapshot": case_record.pre_action_snapshot,
            "audits": audits,
            "events": events,
        },
        ensure_ascii=False,
        default=str,
    )
    for forbidden in (
        "不应进入案件或事件的正文",
        "附图说明",
        "appeal.png",
        str(author.email),
        str(other.email),
        "198.51.100.216",
        asset.storage_key,
        str(isolated_media_root),
    ):
        assert forbidden not in serialized


def _account_deleted_event(account_id, *, event_id=None, now=None):
    return EventEnvelope(
        event_id=event_id or new_ulid(),
        event_type="account.deleted.v1",
        schema_version=1,
        occurred_at=now or datetime(2026, 7, 25, 5, 0, tzinfo=UTC),
        actor_id=uuid4(),
        aggregate_type="account",
        aggregate_id=str(account_id),
        trace_code=new_trace_code(),
        payload={
            "deletion_id": new_ulid(),
            "was_author": True,
            "author_disposition": "delete_all",
            "disposition_id": new_ulid(),
            "article_count": 1,
        },
    )


def test_account_deletion_closes_reports_cases_and_duplicate_is_idempotent() -> None:
    admin = _account("cmt011-admin", administrator=True)
    deleted = _account("cmt011-deleted", author=True)
    survivor = _account("cmt011-survivor")
    target = _account("cmt011-target", author=True)
    article, _ = _article(deleted)
    case_result = _create_case(admin, article, ArticleAction.HIDE)
    article_appeal = appeal_article_action(
        actor_id=deleted.id,
        case_id=case_result.case_id,
        statement="删除账户前的文章申诉",
        evidence_refs=(),
        client_ip="198.51.100.214",
        evidence_gateway=_Evidence(),
    )
    own_report = Report.objects.create(
        target_comment_id=new_ulid(),
        reporter_id=deleted.id,
        reported_author_id=target.id,
        reason="SPAM",
    )
    target_report = Report.objects.create(
        target_comment_id=new_ulid(),
        reporter_id=survivor.id,
        reported_author_id=deleted.id,
        reason="HARASSMENT",
        state="APPEAL_PENDING",
        reviewed_by_id=admin.id,
        reviewed_at=datetime(2026, 7, 25, 4, 0, tzinfo=UTC),
        decision_reason="初审成立",
    )
    report_appeal = ReportAppeal.objects.create(
        report=target_report,
        appellant_id=deleted.id,
        basis_outcome="UPHELD",
    )
    ReportRecoverySnapshot.objects.create(
        report=target_report,
        comment_id=target_report.target_comment_id,
        body="账户删除前的私有恢复正文",
        previous_state="VISIBLE",
        previous_visible_at=datetime(2026, 7, 25, 3, 0, tzinfo=UTC),
    )
    envelope = _account_deleted_event(deleted.id)

    first = consume_account_deleted(envelope)
    duplicate = consume_account_deleted(envelope)

    own_report.refresh_from_db()
    target_report.refresh_from_db()
    report_appeal.refresh_from_db()
    case = ArticleModerationCase.objects.get(pk=case_result.case_id)
    stored_article_appeal = ArticleAppeal.objects.get(pk=article_appeal.appeal_id)
    assert (first.outcome, duplicate.outcome) == (
        ConsumerOutcome.PROCESSED,
        ConsumerOutcome.ALREADY_PROCESSED,
    )
    assert (own_report.state, own_report.closure_reason) == (
        "CLOSED",
        "REPORTER_DELETED",
    )
    assert (target_report.state, target_report.closure_reason) == (
        "CLOSED",
        "REPORTED_ACCOUNT_DELETED",
    )
    assert report_appeal.state == "CLOSED"
    assert not ReportRecoverySnapshot.objects.filter(report=target_report).exists()
    assert (case.state, stored_article_appeal.state) == ("CLOSED", "CLOSED")
    identity = DeletedAccountIdentity.objects.get(account_id=deleted.id)
    assert identity.deletion_id == envelope.payload["deletion_id"]
    assert set(field.name for field in identity._meta.fields) == {
        "account_id",
        "deletion_id",
        "deleted_at",
    }
    events = apps.get_model("core", "OutboxEvent").objects.filter(
        event_type="report.closed.v1"
    )
    assert events.count() == 1
    assert events.get().payload["recipient_id"] == str(survivor.id)


def test_physical_article_and_comment_purge_retains_moderation_records() -> None:
    now = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
    admin = _account("cmt011-admin", administrator=True)
    author = _account("cmt011-author", author=True)
    reporter = _account("cmt011-reporter")
    article, _ = _article(author)
    thread = apps.get_model("comments", "DiscussionThread").objects.create(
        target_type="ARTICLE",
        target_id=article.id,
        owner=author,
    )
    comment_id = new_ulid()
    comment = apps.get_model("comments", "Comment").objects.create(
        id=comment_id,
        thread=thread,
        root_id=comment_id,
        author=author,
        author_kind="ACCOUNT",
        body="物理清理后不保留的评论",
        state="VISIBLE",
        created_at=now - timedelta(minutes=30),
        visible_at=now - timedelta(minutes=20),
        depth=0,
        reply_count=0,
        client_ip="192.0.2.215",
    )
    report = Report.objects.create(
        target_comment_id=comment.id,
        reporter_id=reporter.id,
        reported_author_id=author.id,
        reason="IRRELEVANT",
        state="APPEAL_PENDING",
        reviewed_by_id=admin.id,
        reviewed_at=now,
        decision_reason="初审成立",
    )
    report_appeal = ReportAppeal.objects.create(
        report=report,
        appellant_id=author.id,
        basis_outcome="UPHELD",
    )
    case_result = create_article_moderation_case(
        actor_id=admin.id,
        article_id=article.id,
        action=ArticleAction.DELETE,
        reason="删除并等待物理清理",
        **_context(clock=FrozenClock(now)),
    )
    article_appeal = appeal_article_action(
        actor_id=author.id,
        case_id=case_result.case_id,
        statement="物理清理后保留的文章申诉",
        evidence_refs=(),
        client_ip="198.51.100.217",
        evidence_gateway=_Evidence(),
    )
    case = ArticleModerationCase.objects.get(pk=case_result.case_id)
    deleted = Article.objects.get(pk=article.id)

    result = purge_deleted_article(
        article_id=article.id,
        expected_purge_after=deleted.purge_after,
        clock=FrozenClock(deleted.purge_after),
    )

    assert result.outcome.value == "purged"
    assert not Article.objects.filter(pk=article.id).exists()
    assert (
        not apps.get_model("comments", "Comment").objects.filter(pk=comment.id).exists()
    )
    assert ArticleModerationCase.objects.filter(pk=case.id).exists()
    assert ArticleAppeal.objects.filter(pk=article_appeal.appeal_id).exists()
    assert Report.objects.filter(pk=report.id).exists()
    assert ReportAppeal.objects.filter(pk=report_appeal.id).exists()
