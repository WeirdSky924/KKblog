from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connections, transaction

from apps.learning.public import (
    GenerationQuestionTypes,
    KnowledgePointDraft,
    LearningCommandError,
    QuestionBankCoverageState,
    QuestionBankPublicationDraft,
    QuestionDraft,
    QuestionOptionDraft,
    QuestionType,
    VolumeDraft,
    create_question_bank_generation_request,
    publish_question_bank_generation,
    revise_question_bank,
)

from .test_account_documents_backend import _approved
from .test_documents_lifecycle import _account
from .test_question_generation_runtime import _configured_generation_profile

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def generation_profile():
    return _configured_generation_profile()


def _request(root, owner, *, key="bank:generation"):
    apps.get_model("learning", "LearningQuotaPolicy").objects.update(
        max_questions_per_volume=4
    )
    document, _, _ = _approved(root, owner, key=f"document:{key}")
    return create_question_bank_generation_request(
        owner_id=owner.id,
        document_id=document.document_id,
        base_title="Python 基础",
        description="覆盖语法与运行时基础。",
        question_types=GenerationQuestionTypes(
            single_choice=True,
            multiple_choice=True,
            true_false=True,
            short_answer=True,
        ),
        idempotency_key=key,
        dispatcher=lambda _series_id: None,
    )


def _points():
    return (
        KnowledgePointDraft("kp-1", "变量与对象", 100),
        KnowledgePointDraft("kp-2", "集合操作", 90),
        KnowledgePointDraft("kp-3", "布尔判断", 80),
        KnowledgePointDraft("kp-4", "函数设计", 70),
    )


def _questions():
    return (
        QuestionDraft(
            logical_id="q-1",
            ordinal=1,
            question_type=QuestionType.SINGLE_CHOICE,
            stem_markdown="Python 变量绑定的对象是什么？",
            options=(
                QuestionOptionDraft("a", "名称"),
                QuestionOptionDraft("b", "对象"),
            ),
            correct_option_ids=("b",),
            boolean_answer=None,
            reference_answer="",
            scoring_points=(),
            explanation_markdown="变量名绑定到对象。",
            knowledge_point_ids=("kp-1",),
        ),
        QuestionDraft(
            logical_id="q-2",
            ordinal=2,
            question_type=QuestionType.MULTIPLE_CHOICE,
            stem_markdown="哪些是集合类型？",
            options=(
                QuestionOptionDraft("a", "list"),
                QuestionOptionDraft("b", "set"),
                QuestionOptionDraft("c", "int"),
            ),
            correct_option_ids=("a", "b"),
            boolean_answer=None,
            reference_answer="",
            scoring_points=(),
            explanation_markdown="list 与 set 都是集合。",
            knowledge_point_ids=("kp-2",),
        ),
        QuestionDraft(
            logical_id="q-3",
            ordinal=3,
            question_type=QuestionType.TRUE_FALSE,
            stem_markdown="空列表的布尔值为假。",
            options=(),
            correct_option_ids=(),
            boolean_answer=True,
            reference_answer="",
            scoring_points=(),
            explanation_markdown="空容器的布尔值为假。",
            knowledge_point_ids=("kp-3",),
        ),
        QuestionDraft(
            logical_id="q-4",
            ordinal=4,
            question_type=QuestionType.SHORT_ANSWER,
            stem_markdown="说明函数单一职责原则。",
            options=(),
            correct_option_ids=(),
            boolean_answer=None,
            reference_answer="一个函数聚焦完成一个清晰职责。",
            scoring_points=("职责边界清晰", "避免无关副作用"),
            explanation_markdown="回答需要说明边界与副作用。",
            knowledge_point_ids=("kp-4",),
        ),
    )


def test_publish_complete_revision_questions_and_independent_tags(
    isolated_media_root,
) -> None:
    owner = _account("bank-schema")
    request = _request(isolated_media_root, owner)
    published = publish_question_bank_generation(
        owner_id=owner.id,
        series_id=request.series_id,
        expected_series_version=request.row_version,
        publication=QuestionBankPublicationDraft(
            knowledge_points=_points(),
            volumes=(VolumeDraft(1, _questions()),),
            omitted_knowledge_point_ids=(),
            tag_names=("Python", " python ", "编程基础"),
        ),
    )
    series_model = apps.get_model("learning", "QuestionBankSeries")
    bank_model = apps.get_model("learning", "QuestionBank")
    revision_model = apps.get_model("learning", "QuestionBankRevision")
    question_model = apps.get_model("learning", "Question")
    tag_model = apps.get_model("learning", "QuestionBankTag")
    series = series_model.objects.get(pk=request.series_id)
    bank = bank_model.objects.get(series=series, volume_number=1)
    revision = revision_model.objects.get(bank=bank, sequence=1)

    assert published.coverage_state == QuestionBankCoverageState.COMPLETE
    assert published.volume_count == 1
    assert series.total_knowledge_points == 4
    assert series.covered_knowledge_points == 4
    assert series.omitted_knowledge_points == 0
    assert bank.current_revision_id == revision.id
    assert revision.question_count == 4
    assert question_model.objects.filter(revision=revision).count() == 4
    assert tag_model.objects.count() == 2
    assert set(tag_model.objects.values_list("normalized_name", flat=True)) == {
        "python",
        "编程基础",
    }
    assert all(tag.usage_count == 1 for tag in tag_model.objects.all())

    revision.reason = "mutate history"
    with pytest.raises(ValidationError):
        revision.save()
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            revision_model.objects.filter(pk=revision.id).update(
                reason="bypass model save"
            )
    question = question_model.objects.filter(revision=revision).first()
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            question_model.objects.filter(pk=question.id).update(
                stem_markdown="bypass model save"
            )


def test_invalid_question_or_half_volume_publishes_nothing(
    isolated_media_root,
) -> None:
    owner = _account("bank-invalid")
    request = _request(isolated_media_root, owner, key="bank:invalid")
    invalid_multiple = replace(
        _questions()[1],
        correct_option_ids=("a", "b", "c"),
    )
    publication = QuestionBankPublicationDraft(
        knowledge_points=_points(),
        volumes=(
            VolumeDraft(1, (_questions()[0], invalid_multiple)),
            VolumeDraft(2, (_questions()[2], _questions()[3])),
        ),
        omitted_knowledge_point_ids=(),
        tag_names=("Python",),
    )

    with pytest.raises(LearningCommandError) as captured:
        publish_question_bank_generation(
            owner_id=owner.id,
            series_id=request.series_id,
            expected_series_version=request.row_version,
            publication=publication,
        )
    assert captured.value.code == "learning.question_schema_invalid.v1"
    assert not apps.get_model("learning", "QuestionBank").objects.exists()
    assert not apps.get_model("learning", "Question").objects.exists()


def test_partial_two_volume_coverage_and_full_revision_replacement(
    isolated_media_root,
) -> None:
    owner = _account("bank-partial")
    request = _request(isolated_media_root, owner, key="bank:partial")
    extra_point = KnowledgePointDraft("kp-5", "生成器", 60)
    published = publish_question_bank_generation(
        owner_id=owner.id,
        series_id=request.series_id,
        expected_series_version=request.row_version,
        publication=QuestionBankPublicationDraft(
            knowledge_points=(*_points(), extra_point),
            volumes=(
                VolumeDraft(1, _questions()[:2]),
                VolumeDraft(
                    2,
                    tuple(
                        replace(question, ordinal=index)
                        for index, question in enumerate(_questions()[2:], start=1)
                    ),
                ),
            ),
            omitted_knowledge_point_ids=("kp-5",),
            tag_names=("Python",),
        ),
    )
    assert published.coverage_state == QuestionBankCoverageState.PARTIAL
    assert published.volume_count == 2
    assert published.covered_count == 4 and published.omitted_count == 1

    bank = apps.get_model("learning", "QuestionBank").objects.get(
        series_id=request.series_id,
        volume_number=1,
    )
    first_revision_id = bank.current_revision_id
    revised_questions = tuple(
        replace(question, stem_markdown=f"修订：{question.stem_markdown}")
        for question in _questions()[:2]
    )
    revised = revise_question_bank(
        actor_id=owner.id,
        bank_id=bank.id,
        expected_bank_version=bank.row_version,
        questions=revised_questions,
        revision_reason="修正题干表达",
    )
    bank.refresh_from_db()
    assert revised.sequence == 2
    assert bank.current_revision_id != first_revision_id
    assert (
        apps.get_model("learning", "QuestionBankRevision")
        .objects.filter(bank=bank)
        .count()
        == 2
    )
    other_bank = apps.get_model("learning", "QuestionBank").objects.get(
        series_id=request.series_id,
        volume_number=2,
    )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            apps.get_model("learning", "QuestionBank").objects.filter(
                pk=bank.id
            ).update(current_revision_id=other_bank.current_revision_id)


def test_revision_cannot_drop_the_current_volume_knowledge_point_coverage(
    isolated_media_root,
) -> None:
    owner = _account("bank-revision-coverage")
    request = _request(
        isolated_media_root,
        owner,
        key="bank:revision-coverage",
    )
    publish_question_bank_generation(
        owner_id=owner.id,
        series_id=request.series_id,
        expected_series_version=request.row_version,
        publication=QuestionBankPublicationDraft(
            knowledge_points=_points(),
            volumes=(VolumeDraft(1, _questions()),),
            omitted_knowledge_point_ids=(),
            tag_names=("Python",),
        ),
    )
    bank = apps.get_model("learning", "QuestionBank").objects.get(
        series_id=request.series_id
    )

    with pytest.raises(LearningCommandError) as captured:
        revise_question_bank(
            actor_id=owner.id,
            bank_id=bank.id,
            expected_bank_version=bank.row_version,
            questions=_questions()[:1],
            revision_reason="错误删除了其余知识点",
        )

    assert captured.value.code == "learning.question_schema_invalid.v1"
    bank.refresh_from_db()
    assert bank.revisions.count() == 1
    assert bank.current_revision.sequence == 1


def test_existing_normalized_tag_usage_is_atomic_during_concurrent_publication(
    isolated_media_root,
) -> None:
    owners = tuple(_account(f"bank-tag-race-{index}") for index in range(3))
    requests = tuple(
        _request(
            isolated_media_root,
            owner,
            key=f"bank:tag-race-{index}",
        )
        for index, owner in enumerate(owners)
    )

    def publish(index: int) -> None:
        connections.close_all()
        try:
            publish_question_bank_generation(
                owner_id=owners[index].id,
                series_id=requests[index].series_id,
                expected_series_version=requests[index].row_version,
                publication=QuestionBankPublicationDraft(
                    knowledge_points=_points(),
                    volumes=(VolumeDraft(1, _questions()),),
                    omitted_knowledge_point_ids=(),
                    tag_names=(" Python ",),
                ),
            )
        finally:
            connections.close_all()

    publish(0)
    with ThreadPoolExecutor(max_workers=2) as executor:
        tuple(executor.map(publish, (1, 2)))

    tag_model = apps.get_model("learning", "QuestionBankTag")
    assignment_model = apps.get_model("learning", "QuestionBankTagAssignment")
    tag = tag_model.objects.get(normalized_name="python")
    assert tag_model.objects.count() == 1
    assert assignment_model.objects.count() == 3
    assert tag.usage_count == 3
    assert tag.source == tag_model.Source.REUSED
