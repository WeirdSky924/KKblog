from datetime import UTC, date, datetime

import pytest
from django.apps import apps

from apps.learning.public import (
    GenerationQuestionTypes,
    KnowledgePointDraft,
    PublicQuestionBankFilterError,
    PublicQuestionBankFilters,
    PublicQuestionBankSort,
    QuestionBankNotFound,
    QuestionBankPublicationDraft,
    QuestionDraft,
    QuestionOptionDraft,
    QuestionType,
    VolumeDraft,
    create_question_bank_generation_request,
    public_question_bank_detail,
    public_question_bank_filter_options,
    public_question_bank_page,
    publish_question_bank_generation,
    set_question_bank_visibility,
)

from .test_account_documents_backend import _approved
from .test_documents_lifecycle import _account
from .test_question_generation_runtime import (
    _configure_limit,
    _configured_generation_profile,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _questions(types: tuple[str, ...]):
    result = []
    for ordinal, question_type in enumerate(types, start=1):
        if question_type == QuestionType.SINGLE_CHOICE:
            result.append(
                QuestionDraft(
                    f"q-{ordinal}",
                    ordinal,
                    question_type,
                    f"单选题 {ordinal}",
                    (
                        QuestionOptionDraft("a", "答案 A"),
                        QuestionOptionDraft("b", "答案 B"),
                    ),
                    ("a",),
                    None,
                    "",
                    (),
                    "单选解析",
                    (f"kp-{ordinal}",),
                )
            )
        elif question_type == QuestionType.TRUE_FALSE:
            result.append(
                QuestionDraft(
                    f"q-{ordinal}",
                    ordinal,
                    question_type,
                    f"判断题 {ordinal}",
                    (),
                    (),
                    True,
                    "",
                    (),
                    "判断解析",
                    (f"kp-{ordinal}",),
                )
            )
        else:
            result.append(
                QuestionDraft(
                    f"q-{ordinal}",
                    ordinal,
                    question_type,
                    f"简答题 {ordinal}",
                    (),
                    (),
                    None,
                    "参考答案",
                    ("评分要点",),
                    "简答解析",
                    (f"kp-{ordinal}",),
                )
            )
    return tuple(result)


def _published(
    root,
    owner,
    *,
    key: str,
    title: str,
    description: str,
    tags: tuple[str, ...],
    types: tuple[str, ...],
    published_at: datetime,
    completed_attempts: int = 0,
):
    document, _, _ = _approved(root, owner, key=f"document:{key}")
    request = create_question_bank_generation_request(
        owner_id=owner.id,
        document_id=document.document_id,
        base_title=title,
        description=description,
        question_types=GenerationQuestionTypes(
            single_choice=QuestionType.SINGLE_CHOICE in types,
            multiple_choice=QuestionType.MULTIPLE_CHOICE in types,
            true_false=QuestionType.TRUE_FALSE in types,
            short_answer=QuestionType.SHORT_ANSWER in types,
        ),
        idempotency_key=f"generation:{key}",
        dispatcher=lambda _series_id: None,
        now=published_at,
    )
    questions = _questions(types)
    publish_question_bank_generation(
        owner_id=owner.id,
        series_id=request.series_id,
        expected_series_version=request.row_version,
        publication=QuestionBankPublicationDraft(
            knowledge_points=tuple(
                KnowledgePointDraft(f"kp-{index}", f"知识点 {index}", 100 - index)
                for index in range(1, len(questions) + 1)
            ),
            volumes=(VolumeDraft(1, questions),),
            omitted_knowledge_point_ids=(),
            tag_names=tags,
        ),
        now=published_at,
    )
    bank = apps.get_model("learning", "QuestionBank").objects.get(
        series_id=request.series_id
    )
    bank.completed_attempt_count = completed_attempts
    bank.save(update_fields=("completed_attempt_count", "updated_at"))
    return bank


def _fixture_banks(root):
    administrator, _ = _configured_generation_profile()
    _configure_limit(10, administrator=administrator)
    first = _account("public-bank-first")
    second = _account("public-bank-second")
    third = _account("public-bank-third")
    first.nickname = "Python作者"
    first.save(update_fields=("nickname", "updated_at"))
    banks = (
        _published(
            root,
            first,
            key="public-first",
            title="Python 后端基础",
            description="服务端与数据结构。",
            tags=("Python", "后端"),
            types=(QuestionType.SINGLE_CHOICE,),
            published_at=datetime(2026, 7, 1, 8, tzinfo=UTC),
            completed_attempts=7,
        ),
        _published(
            root,
            second,
            key="public-second",
            title="前端交互实践",
            description="浏览器交互与状态。",
            tags=("前端", "Web"),
            types=(QuestionType.TRUE_FALSE, QuestionType.SHORT_ANSWER),
            published_at=datetime(2026, 7, 2, 8, tzinfo=UTC),
            completed_attempts=3,
        ),
        _published(
            root,
            third,
            key="public-third",
            title="Python 工程进阶",
            description="工程化实践。",
            tags=("Python", "工程"),
            types=(
                QuestionType.SINGLE_CHOICE,
                QuestionType.TRUE_FALSE,
                QuestionType.SHORT_ANSWER,
            ),
            published_at=datetime(2026, 7, 3, 8, tzinfo=UTC),
            completed_attempts=1,
        ),
    )
    return banks


def test_public_page_default_sort_and_visibility_are_stable(
    isolated_media_root,
) -> None:
    first, second, third = _fixture_banks(isolated_media_root)
    hidden = set_question_bank_visibility(
        actor_id=third.series.owner_id,
        bank_id=third.id,
        expected_version=third.row_version,
        target="OWNER_HIDDEN",
    )

    page = public_question_bank_page(filters=PublicQuestionBankFilters())

    assert tuple(item.bank_id for item in page.items) == (second.id, first.id)
    assert page.total_items == 2
    assert all(item.visibility == "PUBLISHED" for item in page.items)
    options = public_question_bank_filter_options()
    assert "工程" not in {tag.name for tag in options.tags}
    assert third.series.owner_id not in {
        author.account_id for author in options.authors
    }
    with pytest.raises(QuestionBankNotFound):
        public_question_bank_detail(bank_id=hidden.id)


def test_filter_groups_use_or_within_and_across_groups(
    isolated_media_root,
) -> None:
    first, second, third = _fixture_banks(isolated_media_root)
    tag_model = apps.get_model("learning", "QuestionBankTag")
    python_tag = tag_model.objects.get(normalized_name="python")
    frontend_tag = tag_model.objects.get(normalized_name="前端")

    page = public_question_bank_page(
        filters=PublicQuestionBankFilters(
            tag_ids=(python_tag.id, frontend_tag.id),
            question_types=(QuestionType.TRUE_FALSE,),
            min_questions=2,
            max_questions=3,
            published_from=date(2026, 7, 2),
            published_to=date(2026, 7, 3),
        )
    )

    assert tuple(item.bank_id for item in page.items) == (third.id, second.id)
    author_page = public_question_bank_page(
        filters=PublicQuestionBankFilters(author_id=first.series.owner_id)
    )
    assert tuple(item.bank_id for item in author_page.items) == (first.id,)


def test_fuzzy_search_and_all_public_sorts_are_deterministic(
    isolated_media_root,
) -> None:
    first, second, third = _fixture_banks(isolated_media_root)
    fuzzy = public_question_bank_page(filters=PublicQuestionBankFilters(query="Pythn"))
    assert {item.bank_id for item in fuzzy.items} == {first.id, third.id}

    most_completed = public_question_bank_page(
        filters=PublicQuestionBankFilters(sort=PublicQuestionBankSort.MOST_COMPLETED)
    )
    assert tuple(item.bank_id for item in most_completed.items) == (
        first.id,
        second.id,
        third.id,
    )
    most_questions = public_question_bank_page(
        filters=PublicQuestionBankFilters(
            sort=PublicQuestionBankSort.QUESTION_COUNT_DESC
        )
    )
    assert tuple(item.bank_id for item in most_questions.items) == (
        third.id,
        second.id,
        first.id,
    )
    fewest_questions = public_question_bank_page(
        filters=PublicQuestionBankFilters(
            sort=PublicQuestionBankSort.QUESTION_COUNT_ASC
        )
    )
    assert tuple(item.bank_id for item in fewest_questions.items) == (
        first.id,
        second.id,
        third.id,
    )


def test_public_detail_contains_current_revision_answers_without_source_document(
    isolated_media_root,
) -> None:
    first, _, _ = _fixture_banks(isolated_media_root)

    detail = public_question_bank_detail(bank_id=first.id)

    assert detail.bank_id == first.id
    assert detail.title == "Python 后端基础"
    assert detail.question_count == 1
    assert detail.questions[0].correct_option_ids == ("a",)
    assert detail.questions[0].explanation_markdown == "单选解析"
    assert not hasattr(detail, "source_document_id")


@pytest.mark.parametrize(
    "filters",
    (
        PublicQuestionBankFilters(page=0),
        PublicQuestionBankFilters(min_questions=5, max_questions=2),
        PublicQuestionBankFilters(question_types=("UNKNOWN",)),
        PublicQuestionBankFilters(
            published_from=date(2026, 7, 3),
            published_to=date(2026, 7, 2),
        ),
    ),
)
def test_invalid_public_filter_dto_fails_closed(filters) -> None:
    with pytest.raises(PublicQuestionBankFilterError):
        public_question_bank_page(filters=filters)
