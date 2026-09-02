from datetime import UTC, datetime

import pytest
from django.apps import apps
from django.urls import reverse

from apps.learning.contracts import QuestionType
from apps.learning.public import wrong_question_quiz_configuration
from apps.learning.services.quizzes import start_wrong_question_attempt

from .test_account_documents_http import _authenticate
from .test_public_question_bank_queries import _fixture_banks

pytestmark = pytest.mark.django_db(transaction=True)


def test_selecting_a_bank_returns_only_the_configuration_panel(
    client, isolated_media_root
):
    first, _, _ = _fixture_banks(isolated_media_root)
    _authenticate(client, first.series.owner)
    url = reverse("learning:quiz-index")

    initial = client.get(url)
    initial_html = initial.content.decode("utf-8")
    assert initial.status_code == 200
    assert 'id="quiz-workspace"' in initial_html
    assert 'id="quiz-config"' in initial_html
    assert 'hx-target="#quiz-config"' in initial_html
    assert 'hx-select="#quiz-config"' in initial_html
    assert 'hx-swap="outerHTML"' in initial_html
    assert "quiz-picker-layout--solo" in initial_html

    selected = client.get(
        f"{url}?bank_id={first.id}",
        HTTP_HX_REQUEST="true",
    )
    selected_html = selected.content.decode("utf-8")
    assert selected.status_code == 200
    assert selected_html.startswith('<div id="quiz-workspace"')
    assert 'id="quiz-config"' in selected_html
    assert "quiz-config__form" in selected_html
    assert "配置答题" in selected_html


def test_wrong_question_configuration_starts_a_wrong_question_attempt(
    isolated_media_root,
):
    bank, _, _ = _fixture_banks(isolated_media_root)
    owner = bank.series.owner
    question = bank.current_revision.questions.get()
    now = datetime(2026, 8, 30, 8, tzinfo=UTC)
    source_key = f"{bank.id}:wrong:one"
    apps.get_model("learning", "WrongQuestion").objects.create(
        account=owner,
        bank=bank,
        question=question,
        source_key=source_key,
        bank_title=bank.series.base_title,
        owner_display_name=owner.nickname or owner.email.partition("@")[0],
        logical_id=question.logical_id,
        question_type=question.question_type,
        stem_markdown=question.stem_markdown,
        options=list(question.options),
        correct_option_ids=list(question.correct_option_ids),
        boolean_answer=question.boolean_answer,
        reference_answer=question.reference_answer,
        scoring_points=list(question.scoring_points),
        explanation_markdown=question.explanation_markdown,
        first_wrong_at=now,
        last_wrong_at=now,
        status_changed_at=now,
    )

    configuration = wrong_question_quiz_configuration(
        account_id=owner.id,
        bank_id=bank.id,
    )
    started = start_wrong_question_attempt(
        account_id=owner.id,
        bank_id=bank.id,
        expected_revision_id=configuration.revision_id,
        expected_source_keys=configuration.source_keys,
        question_types=(QuestionType.SINGLE_CHOICE,),
        question_count=1,
        random_questions=False,
        random_options=False,
        now=now,
    )

    attempt = apps.get_model("learning", "QuizAttempt").objects.get(
        pk=started.attempt_id
    )
    assert attempt.source == "WRONG_QUESTIONS"
    assert attempt.question_count == 1
