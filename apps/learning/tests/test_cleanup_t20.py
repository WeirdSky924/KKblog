from datetime import UTC, datetime, timedelta

import pytest
from django.apps import apps

from apps.accounts.deletion import AccountDeletionDisposition, AuthorArticleDecision
from apps.accounts.services.lifecycle import delete_account
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.learning.contracts import QuestionType
from apps.learning.public import (
    cleanup_learning_expired,
    delete_question_bank,
    purge_account_learning_data,
    purge_due_question_bank,
)
from apps.learning.services.quizzes import (
    save_quiz_response,
    start_quiz_attempt,
    submit_quiz_attempt,
)

from .test_documents_lifecycle import _account
from .test_public_question_bank_queries import _published
from .test_question_generation_runtime import (
    _configure_limit,
    _configured_generation_profile,
)

pytestmark = pytest.mark.django_db(transaction=True)
NOW = datetime(2026, 8, 18, 8, tzinfo=UTC)


def _bank(root, label):
    administrator, _ = _configured_generation_profile()
    _configure_limit(10, administrator=administrator)
    owner = _account(f"{label}-owner")
    bank = _published(
        root,
        owner,
        key=label,
        title="清理题库",
        description="清理测试",
        tags=("清理",),
        types=(QuestionType.SINGLE_CHOICE,),
        published_at=NOW,
    )
    return owner, bank


def _other_attempt(other, bank):
    started = start_quiz_attempt(
        account_id=other.id,
        bank_id=bank.id,
        expected_revision_id=bank.current_revision_id,
        question_types=(QuestionType.SINGLE_CHOICE,),
        question_count=1,
        random_questions=False,
        random_options=False,
        now=NOW + timedelta(minutes=1),
    )
    attempt = apps.get_model("learning", "QuizAttempt").objects.get(
        pk=started.attempt_id
    )
    response = attempt.responses.get()
    save_quiz_response(
        account_id=other.id,
        attempt_id=attempt.id,
        response_id=response.id,
        expected_version=response.row_version,
        request_id=f"cleanup:{other.id}",
        answer=["b"],
        now=NOW + timedelta(minutes=2),
    )
    submit_quiz_attempt(
        account_id=other.id,
        attempt_id=attempt.id,
        request_id=f"cleanup-submit:{other.id}",
        now=NOW + timedelta(minutes=3),
    )
    return attempt


def test_due_bank_cleanup_keeps_other_history_as_snapshot(isolated_media_root):
    owner, bank = _bank(isolated_media_root, "t20-bank")
    other = _account("t20-bank-other")
    attempt = _other_attempt(other, bank)
    pending = delete_question_bank(
        actor_id=owner.id,
        bank_id=bank.id,
        expected_version=bank.row_version,
        now=NOW + timedelta(minutes=4),
    )
    not_due = purge_due_question_bank(
        bank_id=bank.id, now=pending.purge_after - timedelta(seconds=1)
    )
    assert not_due.outcome == "not_due"
    deleted = purge_due_question_bank(
        bank_id=bank.id, now=pending.purge_after + timedelta(seconds=1)
    )
    assert deleted.outcome == "deleted"
    attempt.refresh_from_db()
    assert attempt.bank_id is None
    assert attempt.bank_title == "清理题库"


def test_account_learning_cleanup_removes_owned_data_and_anonymizes_other_history(
    isolated_media_root,
):
    owner, bank = _bank(isolated_media_root, "t20-account")
    other = _account("t20-account-other")
    attempt = _other_attempt(other, bank)
    result = purge_account_learning_data(account_id=owner.id)
    assert result["banks"] == 1
    assert result["series"] == 1
    assert (
        not apps.get_model("learning", "QuestionBank")
        .objects.filter(pk=bank.id)
        .exists()
    )
    attempt.refresh_from_db()
    assert attempt.owner_display_name == "已注销用户"
    assert attempt.bank_id is None
    assert (
        not apps.get_model("learning", "KnowledgeDocument")
        .objects.filter(owner_id=owner.id)
        .exists()
    )


def test_expired_cleanup_is_idempotent_for_empty_batches():
    result = cleanup_learning_expired(now=NOW, batch_size=10)
    again = cleanup_learning_expired(now=NOW, batch_size=10)
    assert result == again
    assert result.documents_deleted == 0
    assert result.banks_deleted == 0


def test_account_delete_invokes_learning_terminal_cleanup(isolated_media_root):
    owner, bank = _bank(isolated_media_root, "t20-delete-account")
    administrator = apps.get_model("accounts", "Account").objects.get(
        roles__role="ADMINISTRATOR"
    )
    deletion = delete_account(
        actor_id=administrator.id,
        account_id=owner.id,
        author_disposition=AccountDeletionDisposition(
            disposition_id=new_ulid(),
            account_id=owner.id,
            decision=AuthorArticleDecision.NO_ARTICLES,
            article_count=0,
        ),
        verify_author_disposition=lambda value: value.account_id == owner.id,
        client_ip="127.0.0.1",
        trace_code=new_trace_code(),
        audit_writer=lambda **kwargs: None,
    )
    assert deletion.account_id == owner.id
    assert (
        not apps.get_model("accounts", "Account").objects.filter(pk=owner.id).exists()
    )
    assert (
        not apps.get_model("learning", "QuestionBank")
        .objects.filter(pk=bank.id)
        .exists()
    )
