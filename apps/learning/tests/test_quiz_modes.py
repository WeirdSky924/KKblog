from datetime import UTC, datetime

import pytest
from django.apps import apps
from django.db import connection
from django.urls import reverse

from apps.learning.contracts import LearningCommandError, QuestionType
from apps.learning.presentation.quiz_forms import QuizStartForm
from apps.learning.queries.quizzes import quiz_attempt_detail
from apps.learning.services import quizzes as quiz_services

from .test_account_documents_http import _authenticate
from .test_documents_lifecycle import _account
from .test_public_question_bank_queries import _published
from .test_question_generation_runtime import (
    _configure_limit,
    _configured_generation_profile,
)

pytestmark = pytest.mark.django_db(transaction=True)
NOW = datetime(2026, 10, 9, 8, tzinfo=UTC)


def _bank(root, label, types):
    administrator, _ = _configured_generation_profile()
    _configure_limit(10, administrator=administrator)
    owner = _account(f"quiz-mode-{label}")
    bank = _published(
        root,
        owner,
        key=f"quiz-mode-{label}",
        title="答题模式题库",
        description="模式回归题库",
        tags=("模式",),
        types=types,
        published_at=NOW,
    )
    return owner, bank


def _start(owner, bank, *, question_types, question_count, mode="EXAM"):
    return quiz_services.start_quiz_attempt(
        account_id=owner.id,
        bank_id=bank.id,
        expected_revision_id=bank.current_revision_id,
        question_types=question_types,
        question_count=question_count,
        random_questions=False,
        random_options=False,
        mode=mode,
        now=NOW,
    )


def test_quiz_attempt_mode_has_database_default_for_previous_app_versions():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_default
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
              AND column_name = 'mode'
            """,
            [apps.get_model("learning", "QuizAttempt")._meta.db_table],
        )
        default = cursor.fetchone()[0]

    assert default == "'EXAM'::character varying"


def test_start_configuration_offers_exam_and_practice_without_changing_question_count(
    client, isolated_media_root
):
    owner, bank = _bank(
        isolated_media_root,
        "start",
        (QuestionType.SINGLE_CHOICE, QuestionType.TRUE_FALSE),
    )
    _authenticate(client, owner)
    url = reverse("learning:quiz-index")

    selected = client.get(url, {"bank_id": str(bank.id)})
    assert selected.status_code == 200
    html = selected.content.decode("utf-8")
    assert 'name="mode"' in html
    assert 'value="EXAM"' in html
    assert 'value="PRACTICE"' in html
    assert QuizStartForm().fields["mode"].initial == "EXAM"

    started = client.post(
        url,
        {
            "bank_id": str(bank.id),
            "expected_revision_id": str(bank.current_revision_id),
            "source": "QUESTION_BANK",
            "question_types": [QuestionType.SINGLE_CHOICE, QuestionType.TRUE_FALSE],
            "question_count": "2",
            "duration_minutes": "30",
            "random_questions": "on",
            "random_options": "on",
            "mode": "PRACTICE",
        },
    )
    assert started.status_code == 302
    attempt = apps.get_model("learning", "QuizAttempt").objects.get(account=owner)
    assert attempt.mode == "PRACTICE"
    assert attempt.question_count == 2

    attempt_url = reverse("learning:quiz-attempt", kwargs={"attempt_id": attempt.id})
    before_submit = client.get(attempt_url)
    assert before_submit.status_code == 200
    before_html = before_submit.content.decode("utf-8")
    assert "data-quiz-practice-submit" in before_html
    assert "quiz-explanation-panel" not in before_html
    assert "quiz-response__submit" not in before_html

    responses = {response.logical_id: response for response in attempt.responses.all()}
    first = responses["q-1"]
    detail = quiz_attempt_detail(account_id=owner.id, attempt_id=attempt.id)
    assert all(item.correct_option_ids is None for item in detail.responses)
    quiz_services.save_quiz_response(
        account_id=owner.id,
        attempt_id=attempt.id,
        response_id=first.id,
        expected_version=first.row_version,
        request_id="practice-autosave-first",
        answer=["a"],
        now=NOW,
    )
    first.refresh_from_db()
    detail = quiz_attempt_detail(account_id=owner.id, attempt_id=attempt.id)
    assert detail.responses[0].answer == ["a"]
    assert detail.responses[0].correct_option_ids is None
    assert detail.responses[0].explanation_markdown is None

    submitted = client.post(
        reverse(
            "learning:quiz-submit-response",
            kwargs={"response_id": first.id},
        ),
        {
            "attempt_id": str(attempt.id),
            "response_id": str(first.id),
            "expected_version": str(first.row_version),
            "request_id": "practice-submit-first",
            "question_type": QuestionType.SINGLE_CHOICE,
            "answer": ["b"],
        },
    )
    assert submitted.status_code == 302
    result = client.get(submitted["Location"])
    assert result.status_code == 200
    html = result.content.decode("utf-8")
    assert "quiz-explanation-panel" in html
    assert html.count("data-quiz-practice-submit") == 1
    assert "单选解析" in html
    assert "判断解析" not in html

    detail = quiz_attempt_detail(account_id=owner.id, attempt_id=attempt.id)
    by_id = {item.logical_id: item for item in detail.responses}
    assert by_id["q-1"].correct_option_ids == ("a",)
    assert by_id["q-1"].is_correct is False
    assert by_id["q-1"].explanation_markdown == "单选解析"
    assert by_id["q-2"].boolean_answer is None
    assert by_id["q-2"].explanation_markdown is None
    with pytest.raises(LearningCommandError):
        quiz_services.save_quiz_response(
            account_id=owner.id,
            attempt_id=attempt.id,
            response_id=first.id,
            expected_version=first.row_version,
            request_id="practice-save-after-submit",
            answer=["a"],
            now=NOW,
        )

    repeated = quiz_services.submit_quiz_response(
        account_id=owner.id,
        attempt_id=attempt.id,
        response_id=first.id,
        expected_version=first.row_version,
        request_id="practice-submit-first",
        answer=["b"],
        now=NOW,
    )
    assert repeated.row_version == by_id["q-1"].row_version
    wrong_model = apps.get_model("learning", "WrongQuestion")
    assert wrong_model.objects.filter(account=owner).count() == 1

    quiz_services.submit_quiz_attempt(
        account_id=owner.id,
        attempt_id=attempt.id,
        request_id="practice-submit-whole-attempt",
        now=NOW,
    )
    assert wrong_model.objects.get(account=owner, logical_id="q-1").wrong_count == 1
    assert wrong_model.objects.get(account=owner, logical_id="q-2").wrong_count == 1


def test_exam_mode_hides_all_answers_until_whole_attempt_submission(
    isolated_media_root,
):
    owner, bank = _bank(isolated_media_root, "exam", (QuestionType.SINGLE_CHOICE,))
    started = _start(
        owner,
        bank,
        question_types=(QuestionType.SINGLE_CHOICE,),
        question_count=1,
    )
    attempt = apps.get_model("learning", "QuizAttempt").objects.get(
        pk=started.attempt_id
    )
    response = attempt.responses.get()
    assert attempt.mode == "EXAM"

    quiz_services.save_quiz_response(
        account_id=owner.id,
        attempt_id=attempt.id,
        response_id=response.id,
        expected_version=response.row_version,
        request_id="exam-save-answer",
        answer=["a"],
        now=NOW,
    )
    detail = quiz_attempt_detail(account_id=owner.id, attempt_id=attempt.id)
    assert detail.responses[0].correct_option_ids is None
    assert detail.responses[0].explanation_markdown is None
    with pytest.raises(LearningCommandError):
        quiz_services.submit_quiz_response(
            account_id=owner.id,
            attempt_id=attempt.id,
            response_id=response.id,
            expected_version=detail.responses[0].row_version,
            request_id="exam-submit-one-question",
            answer=["a"],
            now=NOW,
        )

    quiz_services.submit_quiz_attempt(
        account_id=owner.id,
        attempt_id=attempt.id,
        request_id="exam-submit-whole-attempt",
        now=NOW,
    )
    detail = quiz_attempt_detail(account_id=owner.id, attempt_id=attempt.id)
    assert detail.responses[0].correct_option_ids == ("a",)
    assert detail.responses[0].is_correct is True
    assert detail.responses[0].explanation_markdown == "单选解析"


def test_practice_short_answer_reveals_reference_and_self_assesses_before_final_submit(
    isolated_media_root,
):
    owner, bank = _bank(isolated_media_root, "short", (QuestionType.SHORT_ANSWER,))
    started = _start(
        owner,
        bank,
        question_types=(QuestionType.SHORT_ANSWER,),
        question_count=1,
        mode="PRACTICE",
    )
    attempt = apps.get_model("learning", "QuizAttempt").objects.get(
        pk=started.attempt_id
    )
    response = attempt.responses.get()

    quiz_services.submit_quiz_response(
        account_id=owner.id,
        attempt_id=attempt.id,
        response_id=response.id,
        expected_version=response.row_version,
        request_id="practice-submit-short",
        answer="自己的简答",
        now=NOW,
    )
    detail = quiz_attempt_detail(account_id=owner.id, attempt_id=attempt.id)
    assert detail.responses[0].reference_answer == "参考答案"
    assert detail.responses[0].scoring_points == ("评分要点",)
    assert detail.responses[0].explanation_markdown == "简答解析"

    assessed = quiz_services.assess_quiz_short_answer(
        account_id=owner.id,
        attempt_id=attempt.id,
        response_id=response.id,
        expected_version=detail.responses[0].row_version,
        request_id="practice-assess-short",
        self_assessment="NOT_MASTERED",
        now=NOW,
    )
    attempt.refresh_from_db()
    assert assessed.self_assessment == "NOT_MASTERED"
    assert attempt.status == "IN_PROGRESS"
    assert attempt.short_answer_mastered is None
    assert (
        apps.get_model("learning", "WrongQuestion")
        .objects.filter(account=owner)
        .count()
        == 1
    )

    submitted = quiz_services.submit_quiz_attempt(
        account_id=owner.id,
        attempt_id=attempt.id,
        request_id="practice-submit-short-attempt",
        now=NOW,
    )
    assert submitted.short_answer_mastered == 0
    assert submitted.short_answer_total == 1
    assert (
        apps.get_model("learning", "WrongQuestion")
        .objects.get(account=owner)
        .wrong_count
        == 1
    )
