from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta

import pytest
from django.apps import apps
from django.db import connections

from apps.core.observability.trace import new_trace_code
from apps.learning.public import (
    GenerationQuestionTypes,
    LearningCommandError,
    LearningQuotaLimits,
    QuestionBankPublicationDraft,
    QuestionBankVisibility,
    VolumeDraft,
    configure_site_quota_policy,
    create_question_bank_generation_request,
    delete_question_bank,
    publish_question_bank_generation,
    restore_question_bank,
    set_question_bank_visibility,
)

from .test_account_documents_backend import _approved
from .test_documents_lifecycle import NOW, _account
from .test_question_banks_schema import _points, _questions
from .test_question_generation_runtime import _configured_generation_profile

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def generation_profile():
    return _configured_generation_profile()


def _types():
    return GenerationQuestionTypes(
        single_choice=True,
        multiple_choice=False,
        true_false=False,
        short_answer=False,
    )


def _request(root, owner, document_id, *, key):
    apps.get_model("learning", "LearningQuotaPolicy").objects.update(
        max_questions_per_volume=20
    )
    return create_question_bank_generation_request(
        owner_id=owner.id,
        document_id=document_id,
        base_title="并发题库",
        description="",
        question_types=_types(),
        idempotency_key=key,
        dispatcher=lambda _series_id: None,
    )


def _published(root, owner, *, key):
    document, _, _ = _approved(root, owner, key=f"document:{key}")
    request = _request(root, owner, document.document_id, key=key)
    publish_question_bank_generation(
        owner_id=owner.id,
        series_id=request.series_id,
        expected_series_version=request.row_version,
        publication=QuestionBankPublicationDraft(
            knowledge_points=_points(),
            volumes=(
                VolumeDraft(
                    1,
                    (
                        replace(
                            _questions()[0],
                            knowledge_point_ids=tuple(
                                point.logical_id for point in _points()
                            ),
                        ),
                    ),
                ),
            ),
            omitted_knowledge_point_ids=(),
            tag_names=("Python",),
        ),
    )
    return apps.get_model("learning", "QuestionBank").objects.get(
        series_id=request.series_id
    )


def test_generation_request_is_idempotent_and_uses_server_snapshot(
    isolated_media_root,
) -> None:
    owner = _account("generation-request")
    document, _, _ = _approved(
        isolated_media_root,
        owner,
        key="document:generation-request",
    )
    first = _request(
        isolated_media_root,
        owner,
        document.document_id,
        key="generation:stable",
    )
    repeated = _request(
        isolated_media_root,
        owner,
        document.document_id,
        key="generation:stable",
    )
    usage = apps.get_model("learning", "LearningDailyUsage").objects.get(
        account=owner,
        generations_accepted__gt=0,
    )
    series = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=first.series_id
    )
    assert repeated.series_id == first.series_id
    assert usage.generations_accepted == 1
    assert series.max_questions_per_volume_snapshot == 20
    assert series.allowed_question_types == ["SINGLE_CHOICE"]
    assert series.reserved_bank_slots == 1

    with pytest.raises(LearningCommandError) as conflict:
        create_question_bank_generation_request(
            owner_id=owner.id,
            document_id=document.document_id,
            base_title="不同标题",
            description="",
            question_types=_types(),
            idempotency_key="generation:stable",
            dispatcher=lambda _series_id: None,
        )
    assert conflict.value.code == "learning.idempotency_conflict.v1"


def test_daily_and_unpurged_bank_quotas_are_atomic(
    isolated_media_root,
    generation_profile,
) -> None:
    administrator, _ = generation_profile
    configure_site_quota_policy(
        actor_id=administrator.id,
        expected_version=1,
        limits=LearningQuotaLimits(
            daily_uploads=10,
            pending_reviews=3,
            daily_generations=1,
            concurrent_model_runs=1,
            unpurged_banks=100,
        ),
        trace_code="KJ-GENERATION-DAILY",
        client_ip="127.0.0.1",
    )
    owner = _account("generation-daily")
    first_doc, _, _ = _approved(
        isolated_media_root,
        owner,
        key="document:generation-daily-1",
    )
    second_doc, _, _ = _approved(
        isolated_media_root,
        owner,
        key="document:generation-daily-2",
        content="# Approved\nSecond daily document\n",
    )
    _request(
        isolated_media_root,
        owner,
        first_doc.document_id,
        key="generation:daily-1",
    )
    with pytest.raises(LearningCommandError) as daily:
        _request(
            isolated_media_root,
            owner,
            second_doc.document_id,
            key="generation:daily-2",
        )
    assert daily.value.code == "learning.daily_generation_quota_exhausted.v1"


def test_concurrent_requests_respect_unpurged_bank_limit(
    isolated_media_root,
    generation_profile,
) -> None:
    administrator, _ = generation_profile
    configure_site_quota_policy(
        actor_id=administrator.id,
        expected_version=1,
        limits=LearningQuotaLimits(
            daily_uploads=10,
            pending_reviews=3,
            daily_generations=10,
            concurrent_model_runs=1,
            unpurged_banks=1,
        ),
        trace_code="KJ-GENERATION-BANK-LIMIT",
        client_ip="127.0.0.1",
    )
    owner = _account("generation-bank-limit")
    documents = tuple(
        _approved(
            isolated_media_root,
            owner,
            key=f"document:generation-bank-{index}",
            content=f"# Approved\nConcurrent document {index}\n",
        )[0]
        for index in range(2)
    )

    def worker(index: int) -> str:
        connections.close_all()
        try:
            _request(
                isolated_media_root,
                owner,
                documents[index].document_id,
                key=f"generation:bank-{index}",
            )
        except LearningCommandError as error:
            return error.code
        finally:
            connections.close_all()
        return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(worker, range(2)))
    assert sorted(outcomes) == ["created", "learning.bank_quota_exhausted.v1"]
    assert apps.get_model("learning", "QuestionBankSeries").objects.count() == 1


def test_two_volume_publication_atomically_reserves_two_bank_slots(
    isolated_media_root,
    generation_profile,
) -> None:
    administrator, _ = generation_profile
    configure_site_quota_policy(
        actor_id=administrator.id,
        expected_version=1,
        limits=LearningQuotaLimits(
            daily_uploads=10,
            pending_reviews=3,
            daily_generations=10,
            concurrent_model_runs=1,
            unpurged_banks=1,
        ),
        trace_code="KJ-GENERATION-TWO-VOLUME-ONE",
        client_ip="127.0.0.1",
    )
    owner = _account("generation-two-volume")
    document, _, _ = _approved(
        isolated_media_root,
        owner,
        key="document:generation-two-volume",
    )
    apps.get_model("learning", "LearningQuotaPolicy").objects.update(
        max_questions_per_volume=4
    )
    request = create_question_bank_generation_request(
        owner_id=owner.id,
        document_id=document.document_id,
        base_title="两卷题库",
        description="",
        question_types=GenerationQuestionTypes(
            single_choice=True,
            multiple_choice=True,
            true_false=True,
            short_answer=True,
        ),
        idempotency_key="generation:two-volume",
        dispatcher=lambda _series_id: None,
    )
    publication = QuestionBankPublicationDraft(
        knowledge_points=_points(),
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
    assert captured.value.code == "learning.bank_quota_exhausted.v1"
    assert not apps.get_model("learning", "QuestionBank").objects.exists()
    assert not apps.get_model("learning", "QuestionBankKnowledgePoint").objects.exists()

    configure_site_quota_policy(
        actor_id=administrator.id,
        expected_version=2,
        limits=LearningQuotaLimits(
            daily_uploads=10,
            pending_reviews=3,
            daily_generations=10,
            concurrent_model_runs=1,
            unpurged_banks=2,
        ),
        trace_code="KJ-GENERATION-TWO-VOLUME-TWO",
        client_ip="127.0.0.1",
    )
    published = publish_question_bank_generation(
        owner_id=owner.id,
        series_id=request.series_id,
        expected_series_version=request.row_version,
        publication=publication,
    )
    series = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=request.series_id
    )
    assert published.volume_count == 2
    assert series.reserved_bank_slots == 2
    assert series.banks.count() == 2


def test_visibility_admin_lock_and_delete_restore_preserve_state(
    isolated_media_root,
    generation_profile,
) -> None:
    owner = _account("bank-visibility")
    administrator, _ = generation_profile
    bank = _published(isolated_media_root, owner, key="bank:visibility")
    assert bank.visibility == QuestionBankVisibility.PUBLISHED

    hidden = set_question_bank_visibility(
        actor_id=owner.id,
        bank_id=bank.id,
        expected_version=bank.row_version,
        target=QuestionBankVisibility.OWNER_HIDDEN,
    )
    restored = set_question_bank_visibility(
        actor_id=owner.id,
        bank_id=bank.id,
        expected_version=hidden.row_version,
        target=QuestionBankVisibility.PUBLISHED,
    )
    admin_hidden = set_question_bank_visibility(
        actor_id=administrator.id,
        bank_id=bank.id,
        expected_version=restored.row_version,
        target=QuestionBankVisibility.ADMIN_HIDDEN,
        reason_code="admin_review",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    with pytest.raises(LearningCommandError) as locked:
        set_question_bank_visibility(
            actor_id=owner.id,
            bank_id=bank.id,
            expected_version=admin_hidden.row_version,
            target=QuestionBankVisibility.PUBLISHED,
        )
    assert locked.value.code == "learning.bank_admin_locked.v1"

    deleted = delete_question_bank(
        actor_id=owner.id,
        bank_id=bank.id,
        expected_version=admin_hidden.row_version,
        now=NOW,
    )
    assert deleted.visibility == QuestionBankVisibility.DELETE_PENDING
    restored_delete = restore_question_bank(
        actor_id=owner.id,
        bank_id=bank.id,
        expected_version=deleted.row_version,
        now=NOW + timedelta(days=1),
    )
    assert restored_delete.visibility == QuestionBankVisibility.ADMIN_HIDDEN
