from datetime import timedelta

import pytest
from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from .test_account_documents_backend import _approved
from .test_documents_lifecycle import NOW, _account

pytestmark = pytest.mark.django_db(transaction=True)


def test_question_generation_runtime_backfills_existing_published_series(
    isolated_media_root,
) -> None:
    owner = _account("generation-migration-owner")
    submitted, _, _ = _approved(
        isolated_media_root,
        owner,
        key="document:generation-migration",
    )
    document_model = apps.get_model("learning", "KnowledgeDocument")
    source_digest = document_model.objects.values_list("content_sha256", flat=True).get(
        pk=submitted.document_id
    )
    published_at = NOW + timedelta(hours=1)

    executor = MigrationExecutor(connection)
    executor.migrate([("learning", "0004_question_bank_facts")])
    try:
        old_apps = executor.loader.project_state(
            [("learning", "0004_question_bank_facts")]
        ).apps
        Series = old_apps.get_model("learning", "QuestionBankSeries")
        Bank = old_apps.get_model("learning", "QuestionBank")
        Revision = old_apps.get_model("learning", "QuestionBankRevision")
        Question = old_apps.get_model("learning", "Question")
        series = Series.objects.create(
            owner_id=owner.id,
            source_document_id=submitted.document_id,
            base_title="历史题库",
            description="",
            allowed_question_types=["SINGLE_CHOICE"],
            max_questions_per_volume_snapshot=4,
            submission_idempotency_key="generation:migration-legacy",
        )
        bank = Bank.objects.create(series=series, volume_number=1)
        revision = Revision.objects.create(
            bank=bank,
            sequence=1,
            question_count=1,
            single_choice_count=1,
            multiple_choice_count=0,
            true_false_count=0,
            short_answer_count=0,
            total_knowledge_points=1,
            covered_knowledge_points=1,
            omitted_knowledge_points=0,
            omitted_knowledge_point_ids=[],
            schema_version="question-bank.v1",
            editor_id=owner.id,
            reason="历史生成",
            content_sha256="0" * 64,
        )
        Question.objects.create(
            revision=revision,
            logical_id="q-1",
            ordinal=1,
            question_type="SINGLE_CHOICE",
            stem_markdown="历史题目",
            options=[{"id": "a", "text": "答案"}, {"id": "b", "text": "干扰"}],
            correct_option_ids=["a"],
            boolean_answer=None,
            reference_answer="",
            scoring_points=[],
            explanation_markdown="历史解析",
            knowledge_point_ids=["kp-1"],
            validation_sha256="1" * 64,
        )
        bank.current_revision = revision
        bank.visibility = "PUBLISHED"
        bank.first_published_at = published_at
        bank.save()
        series.state = "PUBLISHED"
        series.coverage_state = "COMPLETE"
        series.total_knowledge_points = 1
        series.covered_knowledge_points = 1
        series.omitted_knowledge_points = 0
        series.save()

        executor = MigrationExecutor(connection)
        executor.migrate([("learning", "0005_question_generation_runtime")])
        current = apps.get_model("learning", "QuestionBankSeries").objects.get(
            pk=series.id
        )
        policy = apps.get_model("learning", "LearningQuotaPolicy").objects.get(pk=1)
        assert current.input_content_sha256 == source_digest
        assert current.completed_at == published_at
        assert current.started_at <= current.completed_at
        assert current.safe_reason_code == "generation_complete"
        assert current.safe_summary == "题库已完整生成。"
        assert current.generation_snapshot_invocation_id is None
        assert policy.max_questions_per_volume is None
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes("learning"))
