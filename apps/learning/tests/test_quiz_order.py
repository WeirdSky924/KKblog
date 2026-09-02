from types import SimpleNamespace

import pytest
from django.http import QueryDict

from apps.learning.contracts import QuestionType
from apps.learning.presentation.quiz import _navigation_state
from apps.learning.presentation.quiz_forms import QuizStartForm
from apps.learning.services import quizzes


class _DeterministicRandom:
    def sample(self, population, count):
        return list(population)[:count]

    def shuffle(self, values):
        values.reverse()


def _question(logical_id: str, question_type: str):
    return SimpleNamespace(logical_id=logical_id, question_type=question_type)


@pytest.fixture
def mixed_questions():
    return [
        _question("s1", QuestionType.SINGLE_CHOICE),
        _question("m1", QuestionType.MULTIPLE_CHOICE),
        _question("t1", QuestionType.TRUE_FALSE),
        _question("h1", QuestionType.SHORT_ANSWER),
        _question("s2", QuestionType.SINGLE_CHOICE),
        _question("m2", QuestionType.MULTIPLE_CHOICE),
        _question("t2", QuestionType.TRUE_FALSE),
        _question("h2", QuestionType.SHORT_ANSWER),
    ]


def test_select_questions_keeps_type_order_and_shuffles_inside_each_type(
    monkeypatch, mixed_questions
):
    monkeypatch.setattr(quizzes.secrets, "SystemRandom", _DeterministicRandom)

    selected = quizzes._select_questions(
        mixed_questions,
        question_count=len(mixed_questions),
        random_questions=True,
    )

    assert [item.question_type for item in selected] == [
        QuestionType.SINGLE_CHOICE,
        QuestionType.SINGLE_CHOICE,
        QuestionType.MULTIPLE_CHOICE,
        QuestionType.MULTIPLE_CHOICE,
        QuestionType.TRUE_FALSE,
        QuestionType.TRUE_FALSE,
        QuestionType.SHORT_ANSWER,
        QuestionType.SHORT_ANSWER,
    ]
    assert [item.logical_id for item in selected] == [
        "s2",
        "s1",
        "m2",
        "m1",
        "t2",
        "t1",
        "h2",
        "h1",
    ]


def test_select_questions_keeps_type_order_without_randomization(mixed_questions):
    selected = quizzes._select_questions(
        mixed_questions,
        question_count=len(mixed_questions),
        random_questions=False,
    )

    assert [item.logical_id for item in selected] == [
        "s1",
        "s2",
        "m1",
        "m2",
        "t1",
        "t2",
        "h1",
        "h2",
    ]


@pytest.mark.parametrize(
    ("question_type", "answer", "is_correct", "expected"),
    [
        (QuestionType.SINGLE_CHOICE, None, None, "wrong"),
        (QuestionType.SINGLE_CHOICE, ["a"], True, "correct"),
        (QuestionType.SINGLE_CHOICE, ["a"], False, "wrong"),
        (QuestionType.SHORT_ANSWER, "答案", None, "pending"),
    ],
)
def test_submitted_question_navigation_state(
    question_type, answer, is_correct, expected
):
    response = SimpleNamespace(
        question_type=question_type,
        answer=answer,
        is_correct=is_correct,
    )

    assert _navigation_state(response, submitted=True) == expected


def test_quiz_start_form_preserves_multiple_wrong_question_source_keys():
    data = QueryDict("", mutable=True)
    data.update(
        {
            "bank_id": "00000000-0000-0000-0000-000000000001",
            "expected_revision_id": "00000000-0000-0000-0000-000000000002",
            "source": "WRONG_QUESTIONS",
            "question_count": "1",
            "random_questions": "on",
            "random_options": "on",
        }
    )
    data.setlist("question_types", [QuestionType.SINGLE_CHOICE])
    data.setlist("expected_source_keys", ["wrong:one", "wrong:two"])

    form = QuizStartForm(
        data,
        question_type_choices=((QuestionType.SINGLE_CHOICE, "单选（1 题）"),),
    )

    assert form.is_valid()
    assert form.source_keys() == ("wrong:one", "wrong:two")
