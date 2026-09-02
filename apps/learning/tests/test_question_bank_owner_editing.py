from uuid import uuid4

import pytest
from django.apps import apps

from apps.core.ids import new_ulid
from apps.learning.public import (
    GenerationQuestionTypes,
    QuestionContentDraft,
    QuestionOptionDraft,
    create_question_bank_generation_request,
    execute_question_bank_generation,
    mark_question_bank_generation_final_failed,
    retry_question_bank_generation,
    revise_question_in_bank,
    update_question_bank_series_metadata,
)

from .test_account_documents_backend import _approved
from .test_documents_lifecycle import _account
from .test_question_generation_runtime import (
    NOW,
    _configure_limit,
    _configured_generation_profile,
    _gateway,
    _publication_value,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _published(root, owner, *, key: str):
    document, _, storage = _approved(
        root,
        owner,
        key=f"document:{key}",
    )
    request = create_question_bank_generation_request(
        owner_id=owner.id,
        document_id=document.document_id,
        base_title="Python 基础",
        description="初始简介",
        question_types=GenerationQuestionTypes(
            single_choice=True,
            true_false=True,
        ),
        idempotency_key=f"generation:{key}",
        dispatcher=lambda _series_id: None,
        now=NOW,
    )
    gateway, _ = _gateway(_publication_value())
    execute_question_bank_generation(
        series_id=request.series_id,
        task_run_id=new_ulid(),
        gateway=gateway,
        renew_lease=lambda: None,
        storage=storage,
        now=NOW,
    )
    return apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=request.series_id
    )


def test_owner_updates_series_metadata_and_independent_tags_atomically(
    isolated_media_root,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("bank-owner-metadata")
    series = _published(isolated_media_root, owner, key="owner-metadata")
    revision_ids = tuple(series.banks.values_list("current_revision_id", flat=True))

    updated = update_question_bank_series_metadata(
        actor_id=owner.id,
        series_id=series.id,
        expected_version=series.row_version,
        base_title="Python 核心知识",
        description="面向复习的题库。",
        tag_names=("Python", "面试", " python "),
    )

    series.refresh_from_db()
    assert updated.row_version == series.row_version
    assert series.base_title == "Python 核心知识"
    assert series.description == "面向复习的题库。"
    assert set(
        series.tag_assignments.values_list("tag__normalized_name", flat=True)
    ) == {"python", "面试"}
    assert tuple(series.banks.values_list("current_revision_id", flat=True)) == (
        revision_ids
    )


def test_owner_question_edit_creates_full_immutable_revision(
    isolated_media_root,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("bank-owner-question")
    series = _published(isolated_media_root, owner, key="owner-question")
    bank = series.banks.get(volume_number=1)
    first_revision_id = bank.current_revision_id

    revision = revise_question_in_bank(
        actor_id=owner.id,
        bank_id=bank.id,
        expected_bank_version=bank.row_version,
        question=QuestionContentDraft(
            logical_id="q-1",
            stem_markdown="变量名最终绑定到什么？",
            options=(
                QuestionOptionDraft("a", "名称本身"),
                QuestionOptionDraft("b", "对象"),
            ),
            correct_option_ids=("b",),
            boolean_answer=None,
            reference_answer="",
            scoring_points=(),
            explanation_markdown="变量名绑定到对象，而不是名称本身。",
        ),
        revision_reason="修正题干与解释",
    )

    bank.refresh_from_db()
    assert revision.sequence == 2
    assert bank.current_revision_id == revision.id
    assert bank.current_revision_id != first_revision_id
    assert bank.revisions.count() == 2
    assert (
        bank.current_revision.questions.get(logical_id="q-1").stem_markdown
        == "变量名最终绑定到什么?"
    )
    assert (
        bank.revisions.get(pk=first_revision_id)
        .questions.get(logical_id="q-1")
        .stem_markdown
        == "变量绑定的是什么?"
    )


def test_failed_generation_retry_creates_new_series_and_counts_new_request(
    isolated_media_root,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("bank-owner-retry")
    document, _, _ = _approved(
        isolated_media_root,
        owner,
        key="document:owner-retry",
    )
    first = create_question_bank_generation_request(
        owner_id=owner.id,
        document_id=document.document_id,
        base_title="待重试题库",
        description="",
        question_types=GenerationQuestionTypes(single_choice=True),
        idempotency_key="generation:owner-retry:first",
        dispatcher=lambda _series_id: None,
        now=NOW,
    )
    failed = mark_question_bank_generation_final_failed(
        series_id=first.series_id,
        safe_error_code="agents.provider_failed.v1",
        completed_at=NOW,
    )
    failed_series = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=failed.series_id
    )
    calls = []

    retried = retry_question_bank_generation(
        owner_id=owner.id,
        series_id=failed.series_id,
        expected_version=failed_series.row_version,
        idempotency_key=f"generation:owner-retry:{uuid4()}",
        dispatcher=lambda series_id: calls.append(series_id),
        now=NOW,
    )

    assert retried.series_id != first.series_id
    assert calls == [str(retried.series_id)]
    original = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=first.series_id
    )
    replacement = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=retried.series_id
    )
    usage = apps.get_model("learning", "LearningDailyUsage").objects.get(account=owner)
    assert original.state == "GENERATION_FAILED"
    assert replacement.state == "GENERATION_PENDING"
    assert replacement.source_document_id == original.source_document_id
    assert replacement.allowed_question_types == original.allowed_question_types
    assert usage.generations_accepted == 2
