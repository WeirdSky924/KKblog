from datetime import UTC, datetime, timedelta

import pytest
from django.apps import apps
from django.urls import reverse

from apps.learning.contracts import QuestionType
from apps.learning.public import (
    QuizAttemptStatus,
    QuizMasteryStatus,
    iter_quiz_record_csv,
    quiz_record_page,
    request_quiz_record_deletion,
    restore_quiz_record,
    set_wrong_question_mastery,
    wrong_question_page,
)
from apps.learning.services.quizzes import (
    save_quiz_response,
    start_quiz_attempt,
    submit_quiz_attempt,
)

from .test_account_documents_http import _authenticate
from .test_documents_lifecycle import _account
from .test_public_question_bank_queries import _published
from .test_question_generation_runtime import (
    _configure_limit,
    _configured_generation_profile,
)

pytestmark = pytest.mark.django_db(transaction=True)
NOW = datetime(2026, 8, 18, 8, tzinfo=UTC)


def _submitted_wrong(root, label):
    administrator, _ = _configured_generation_profile()
    _configure_limit(10, administrator=administrator)
    owner = _account(label)
    bank = _published(
        root,
        owner,
        key=label,
        title="记录题库",
        description="记录测试",
        tags=("记录",),
        types=(QuestionType.SINGLE_CHOICE,),
        published_at=NOW,
    )
    started = start_quiz_attempt(
        account_id=owner.id,
        bank_id=bank.id,
        expected_revision_id=bank.current_revision_id,
        question_types=(QuestionType.SINGLE_CHOICE,),
        question_count=1,
        random_questions=False,
        random_options=False,
        now=NOW + timedelta(minutes=1),
    )
    attempt_model = apps.get_model("learning", "QuizAttempt")
    response_model = apps.get_model("learning", "QuizResponse")
    attempt = attempt_model.objects.get(pk=started.attempt_id)
    response = response_model.objects.get(attempt=attempt)
    save_quiz_response(
        account_id=owner.id,
        attempt_id=attempt.id,
        response_id=response.id,
        expected_version=response.row_version,
        request_id=f"wrong-{label}",
        answer=["b"],
        now=NOW + timedelta(minutes=2),
    )
    submit_quiz_attempt(
        account_id=owner.id,
        attempt_id=attempt.id,
        request_id=f"submit-{label}",
        now=NOW + timedelta(minutes=3),
    )
    attempt.refresh_from_db()
    return owner, bank, attempt


def test_mastery_is_manual_and_record_deletion_does_not_change_wrong_book(
    isolated_media_root,
):
    owner, bank, attempt = _submitted_wrong(isolated_media_root, "t18-mastery")
    wrong_page = wrong_question_page(account_id=owner.id)
    assert wrong_page.total_items == 1
    wrong = wrong_page.items[0]

    changed = set_wrong_question_mastery(
        account_id=owner.id,
        wrong_question_id=wrong.wrong_question_id,
        expected_version=wrong.row_version,
        mastery_status=QuizMasteryStatus.MASTERED,
        now=NOW + timedelta(minutes=4),
    )
    assert changed.mastery_status == QuizMasteryStatus.MASTERED
    assert wrong_question_page(account_id=owner.id).total_items == 0
    assert (
        wrong_question_page(
            account_id=owner.id, mastery_status=QuizMasteryStatus.MASTERED
        ).total_items
        == 1
    )

    deleted = request_quiz_record_deletion(
        account_id=owner.id,
        attempt_id=attempt.id,
        expected_version=attempt.row_version,
        now=NOW + timedelta(minutes=5),
    )
    assert deleted.status == QuizAttemptStatus.DELETE_PENDING
    assert quiz_record_page(account_id=owner.id).total_items == 0
    assert (
        wrong_question_page(
            account_id=owner.id, mastery_status=QuizMasteryStatus.MASTERED
        )
        .items[0]
        .wrong_count
        == 1
    )


def test_record_restore_and_due_cleanup_keep_a_safe_tombstone(
    isolated_media_root,
):
    owner, _, attempt = _submitted_wrong(isolated_media_root, "t18-cleanup")
    pending = request_quiz_record_deletion(
        account_id=owner.id,
        attempt_id=attempt.id,
        expected_version=attempt.row_version,
        now=NOW + timedelta(minutes=5),
    )
    restored = restore_quiz_record(
        account_id=owner.id,
        attempt_id=attempt.id,
        expected_version=pending.row_version,
        now=NOW + timedelta(minutes=6),
    )
    assert restored.status == QuizAttemptStatus.SUBMITTED
    pending = request_quiz_record_deletion(
        account_id=owner.id,
        attempt_id=attempt.id,
        expected_version=restored.row_version,
        now=NOW + timedelta(minutes=7),
    )
    from apps.learning.public import purge_due_quiz_record

    result = purge_due_quiz_record(
        attempt_id=attempt.id,
        now=pending.purge_after + timedelta(seconds=1),
    )
    assert result.status == QuizAttemptStatus.DELETED
    assert (
        not apps.get_model("learning", "QuizResponse")
        .objects.filter(attempt_id=attempt.id)
        .exists()
    )
    assert quiz_record_page(account_id=owner.id).total_items == 0


def test_csv_is_streamed_for_owner_and_escapes_formula_cells(isolated_media_root):
    owner, _, attempt = _submitted_wrong(isolated_media_root, "t18-csv")
    response = apps.get_model("learning", "QuizResponse").objects.get(attempt=attempt)
    attempt.bank_title = "=危险题库"
    attempt.save(update_fields=("bank_title",))
    response.stem_markdown = "@危险题面"
    response.answer = ["+危险答案"]
    response.save(update_fields=("stem_markdown", "answer"))
    chunks = iter_quiz_record_csv(account_id=owner.id)
    csv_text = "".join(chunks)
    assert "'=危险题库" in csv_text
    assert "'@危险题面" in csv_text
    assert '""+危险答案""' in csv_text
    assert ",+危险答案" not in csv_text
    assert "记录题库" not in csv_text


def test_records_http_requires_login_and_scopes_detail_and_actions(
    isolated_media_root, client
):
    owner, _, attempt = _submitted_wrong(isolated_media_root, "t18-http")
    wrong_url = reverse("learning:wrong-book")
    records_url = reverse("learning:records")
    assert client.get(wrong_url).status_code == 302
    assert client.get(records_url).status_code == 302
    _authenticate(client, owner)
    wrong = client.get(wrong_url)
    records = client.get(records_url)
    assert wrong.status_code == 200
    assert "错题本" in wrong.content.decode("utf-8")
    assert records.status_code == 200
    assert "答题记录" in records.content.decode("utf-8")
    detail = client.get(
        reverse("learning:record-detail", kwargs={"attempt_id": attempt.id})
    )
    assert detail.status_code == 200
    csv_response = client.get(reverse("learning:records-export"))
    assert csv_response.status_code == 200
    assert "题库" in b"".join(csv_response.streaming_content).decode("utf-8")
    other = _account("t18-http-other")
    _authenticate(client, other)
    assert (
        client.get(
            reverse("learning:record-detail", kwargs={"attempt_id": attempt.id})
        ).status_code
        == 404
    )
