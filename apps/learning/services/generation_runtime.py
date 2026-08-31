import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.public import can_upload_attachments
from apps.agents.public import (
    AgentCommandError,
    AgentGateway,
    GatewayError,
    SchemaValidationError,
    bind_agent_invocation_task_run,
    create_agent_invocation_from_snapshot,
    invoke_structured,
)
from apps.core.events import enqueue_event
from apps.core.ids import normalize_ulid
from apps.learning.contracts import (
    KnowledgeDocumentState,
    LearningCommandError,
    LearningModelRunKind,
    QuestionBankPublicationDraft,
    QuestionBankSeriesState,
    QuestionDraft,
    VolumeDraft,
)
from apps.learning.events import GENERATION_FAILED
from apps.learning.generation_schema import question_bank_publication_draft
from apps.learning.models import (
    KnowledgeDocument,
    LearningModelRunReservation,
    QuestionBankSeries,
    QuestionBankTag,
)
from apps.media.public import MediaStorage, MediaTextReadError
from apps.operations.public import RetryableTaskError, TaskCancelled, TaskFinalFailed

from .bank_publication import publish_question_bank_generation
from .document_inputs import knowledge_document_input
from .question_schema import validate_publication
from .quotas import release_learning_model_run, reserve_learning_model_run
from .source_units import (
    SourceKnowledgeUnit,
    batch_source_knowledge_units,
    extract_source_knowledge_units,
)

_SAFE_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*$")
_RETRYABLE_OUTPUT_ERRORS = frozenset(
    {
        "agents.response_schema_invalid.v1",
        "agents.response_semantics_invalid.v1",
    }
)


@dataclass(frozen=True, slots=True)
class QuestionGenerationExecutionResult:
    series_id: UUID
    state: str
    coverage_state: str | None
    volume_count: int
    invocation_id: str | None


@dataclass(frozen=True, slots=True)
class _GenerationClaim:
    owner_id: UUID
    series_version: int
    attempt: int
    allowed_question_types: tuple[str, ...]
    max_questions_per_volume: int
    snapshot_invocation_id: str


def _current_time(now: datetime | None) -> datetime:
    current = now or timezone.now()
    if not isinstance(current, datetime) or not timezone.is_aware(current):
        raise LearningCommandError("learning.time_invalid.v1", "题库生成时间不合法。")
    return current


def _series_identity(value) -> UUID:
    if not isinstance(value, UUID):
        raise LearningCommandError("learning.bank_not_found.v1", "题库不存在。")
    return value


def _task_run_identity(value: str) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise LearningCommandError(
            "learning.generation_task_invalid.v1", "题库生成任务标识不合法。"
        ) from None


def _result(series: QuestionBankSeries) -> QuestionGenerationExecutionResult:
    return QuestionGenerationExecutionResult(
        series_id=series.id,
        state=series.state,
        coverage_state=series.coverage_state,
        volume_count=series.banks.count(),
        invocation_id=series.latest_invocation_id,
    )


def _source(
    *,
    series_id: UUID,
    storage: MediaStorage | None,
) -> tuple[
    QuestionBankSeries,
    tuple[str, ...],
    int,
    tuple[SourceKnowledgeUnit, ...],
]:
    try:
        series = QuestionBankSeries.objects.select_related("source_document").get(
            pk=series_id
        )
    except QuestionBankSeries.DoesNotExist:
        raise LearningCommandError(
            "learning.bank_not_found.v1", "题库不存在。"
        ) from None
    document = series.source_document
    if (
        document.state != KnowledgeDocumentState.APPROVED
        or document.content_sha256 != series.input_content_sha256
    ):
        raise LearningCommandError(
            "learning.document_not_available.v1",
            "知识文档当前不能生成题库。",
        )
    try:
        prepared = knowledge_document_input(document, storage=storage)
    except MediaTextReadError:
        # A copied, missing, or unreadable media object is a source failure,
        # not an AGENT/provider failure. Keep the task error stable and safe.
        raise LearningCommandError(
            "learning.document_not_available.v1",
            "知识文档内容当前不可用。",
        ) from None
    return (
        series,
        prepared.blocks,
        prepared.estimated_tokens,
        extract_source_knowledge_units(prepared.content),
    )


def _claim_generation_attempt(
    *,
    series_id: UUID,
    task_run_id: str,
    chunk_count: int,
    estimated_input_tokens: int,
    now: datetime,
) -> _GenerationClaim:
    with transaction.atomic():
        try:
            series = QuestionBankSeries.objects.select_for_update().get(pk=series_id)
            document = KnowledgeDocument.objects.select_for_update().get(
                pk=series.source_document_id
            )
        except (QuestionBankSeries.DoesNotExist, KnowledgeDocument.DoesNotExist):
            raise LearningCommandError(
                "learning.bank_not_found.v1", "题库不存在。"
            ) from None
        if document.state != KnowledgeDocumentState.APPROVED:
            raise TaskCancelled(result_ref=f"question-generation:{series.id}:source")
        if not can_upload_attachments(series.owner_id):
            raise RetryableTaskError("learning.attachment_capability_required.v1")
        if series.attempt_count >= 3:
            raise LearningCommandError(
                "learning.generation_conflict.v1", "题库生成已达到尝试上限。"
            )
        if not series.generation_snapshot_invocation_id:
            raise LearningCommandError(
                "learning.generation_snapshot_invalid.v1",
                "题库生成配置快照不存在。",
            )
        if series.state == QuestionBankSeriesState.GENERATION_PENDING:
            series.state = QuestionBankSeriesState.GENERATING
            series.started_at = now
            series.task_run_id = task_run_id
        elif (
            series.state != QuestionBankSeriesState.GENERATING
            or series.task_run_id != task_run_id
        ):
            raise LearningCommandError(
                "learning.generation_conflict.v1", "题库生成状态冲突。"
            )
        series.attempt_count += 1
        series.chunk_count = chunk_count
        series.estimated_input_tokens = estimated_input_tokens
        series.last_error_code = ""
        series.row_version += 1
        series.save()
    return _GenerationClaim(
        owner_id=series.owner_id,
        series_version=series.row_version,
        attempt=series.attempt_count,
        allowed_question_types=tuple(series.allowed_question_types),
        max_questions_per_volume=series.max_questions_per_volume_snapshot,
        snapshot_invocation_id=series.generation_snapshot_invocation_id,
    )


def _record_runtime_ids(
    *,
    series_id: UUID,
    task_run_id: str,
    invocation_id: str,
    reservation_id: UUID,
) -> None:
    updated = QuestionBankSeries.objects.filter(
        pk=series_id,
        state=QuestionBankSeriesState.GENERATING,
        task_run_id=task_run_id,
    ).update(
        latest_invocation_id=invocation_id,
        latest_learning_reservation_id=reservation_id,
        last_error_code="",
    )
    if updated != 1:
        raise TaskCancelled(result_ref=f"question-generation:{series_id}:cancelled")


def _record_retry_error(*, series_id: UUID, task_run_id: str, error_code: str) -> None:
    if _SAFE_ERROR_CODE.fullmatch(error_code):
        QuestionBankSeries.objects.filter(
            pk=series_id,
            state=QuestionBankSeriesState.GENERATING,
            task_run_id=task_run_id,
        ).update(last_error_code=error_code)


def _tag_candidates() -> str:
    candidates = []
    for tag in QuestionBankTag.objects.filter(status="ACTIVE").order_by(
        "-usage_count", "normalized_name", "id"
    )[:12]:
        candidate = {"id": str(tag.id), "name": tag.display_name}
        encoded = json.dumps([*candidates, candidate], ensure_ascii=False)
        if len(encoded) > 500:
            break
        candidates.append(candidate)
    return json.dumps(candidates, ensure_ascii=False, separators=(",", ":"))


def _publication_output_validator(
    *,
    allowed_types: tuple[str, ...],
    maximum_questions: int,
    expected_source_unit_ids: tuple[str, ...],
):
    """Apply learning's dynamic publication rules inside the AGENT harness."""

    def validate(value: Mapping[str, object]) -> None:
        try:
            publication = question_bank_publication_draft(value)
            validate_publication(
                publication,
                allowed_types=allowed_types,
                maximum_questions=maximum_questions,
                allow_empty_questions=True,
            )
            expected_sources = set(expected_source_unit_ids)
            for point in publication.knowledge_points:
                source_ids = set(point.source_unit_ids)
                if not source_ids or not source_ids <= expected_sources:
                    raise SchemaValidationError(
                        "agents.response_semantics_invalid.v1",
                        expected="each knowledge point cites source units from this batch",
                    )
        except LearningCommandError as error:
            raise SchemaValidationError(
                "agents.response_semantics_invalid.v1",
                expected=error.code,
            ) from None

    return validate


def _source_batch_material(units: tuple[SourceKnowledgeUnit, ...]) -> str:
    entries = [
        {
            "source_unit_id": unit.logical_id,
            "source_order": unit.ordinal,
            "heading": unit.heading,
            "content": unit.content,
        }
        for unit in units
    ]
    return json.dumps(
        entries,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _scoped_identifier(prefix: str, value: str) -> str:
    candidate = f"{prefix}-{value}"
    if len(candidate) <= 64:
        return candidate
    digest = sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"{candidate[:55]}-{digest}"


def _merge_publications(
    *,
    publications: tuple[QuestionBankPublicationDraft, ...],
    units: tuple[SourceKnowledgeUnit, ...],
    maximum_questions_per_volume: int,
) -> QuestionBankPublicationDraft:
    points_by_id = {}
    questions: list[QuestionDraft] = []
    tags: list[str] = []
    for batch_index, publication in enumerate(publications, start=1):
        point_ids = {
            point.logical_id: _scoped_identifier(f"b{batch_index}-kp", point.logical_id)
            for point in publication.knowledge_points
        }
        for point in publication.knowledge_points:
            points_by_id[point_ids[point.logical_id]] = replace(
                point,
                logical_id=point_ids[point.logical_id],
            )
        for volume in publication.volumes:
            for question in volume.questions:
                if not question.knowledge_point_ids:
                    raise LearningCommandError(
                        "learning.question_schema_invalid.v1",
                        "每个题目必须有一个主要知识点。",
                    )
                questions.append(
                    replace(
                        question,
                        logical_id=_scoped_identifier(
                            f"b{batch_index}-q", question.logical_id
                        ),
                        knowledge_point_ids=tuple(
                            point_ids[point_id]
                            for point_id in question.knowledge_point_ids
                        ),
                    )
                )
        for tag in publication.tag_names:
            if tag not in tags and len(tags) < 20:
                tags.append(tag)

    if not points_by_id:
        raise LearningCommandError(
            "learning.question_schema_invalid.v1",
            "AGENT 没有识别出可用知识点。",
        )
    omitted_ids: list[str] = []
    point_order = {point_id: index for index, point_id in enumerate(points_by_id)}
    selected_questions = list(questions)
    max_total = maximum_questions_per_volume * 2
    if len(selected_questions) > max_total:
        selected_questions = sorted(
            selected_questions,
            key=lambda question: (
                -points_by_id[question.knowledge_point_ids[0]].importance,
                point_order[question.knowledge_point_ids[0]],
            ),
        )[:max_total]
    selected_covered_ids = {
        point_id
        for question in selected_questions
        for point_id in question.knowledge_point_ids
    }
    omitted_ids = [
        point_id for point_id in points_by_id if point_id not in selected_covered_ids
    ]
    if not selected_questions:
        raise LearningCommandError(
            "learning.question_schema_invalid.v1",
            "AGENT 识别出的知识点没有可发布题目。",
        )
    normalized_questions: list[QuestionDraft] = []
    logical_id_counts: dict[str, int] = {}
    for ordinal, question in enumerate(selected_questions, start=1):
        primary_id = question.knowledge_point_ids[0]
        logical_id_counts[primary_id] = logical_id_counts.get(primary_id, 0) + 1
        suffix = logical_id_counts[primary_id]
        normalized_questions.append(
            replace(
                question,
                logical_id=_scoped_identifier("q", f"{primary_id}-{suffix}"),
                ordinal=ordinal,
                knowledge_point_ids=question.knowledge_point_ids,
            )
        )
    volumes = []
    for volume_number, start in enumerate(
        range(0, len(normalized_questions), maximum_questions_per_volume),
        start=1,
    ):
        batch = tuple(
            replace(question, ordinal=ordinal)
            for ordinal, question in enumerate(
                normalized_questions[start : start + maximum_questions_per_volume],
                start=1,
            )
        )
        volumes.append(VolumeDraft(volume_number, batch))
    if not volumes:
        raise LearningCommandError(
            "learning.question_schema_invalid.v1", "没有可发布的题目。"
        )
    return QuestionBankPublicationDraft(
        knowledge_points=tuple(points_by_id[point_id] for point_id in points_by_id),
        volumes=tuple(volumes),
        omitted_knowledge_point_ids=tuple(omitted_ids),
        tag_names=tuple(tags or ["知识题库"]),
    )


def _release_active(series: QuestionBankSeries) -> None:
    identities = tuple(
        LearningModelRunReservation.objects.filter(
            account_id=series.owner_id,
            owner_ref__startswith=f"{series.id}:",
            status="ACTIVE",
        ).values_list("id", flat=True)
    )
    for identity in identities:
        release_learning_model_run(reservation_id=identity)


def execute_question_bank_generation(
    *,
    series_id,
    task_run_id: str,
    gateway: AgentGateway,
    renew_lease,
    storage: MediaStorage | None = None,
    now: datetime | None = None,
) -> QuestionGenerationExecutionResult:
    identity = _series_identity(series_id)
    stable_task_run_id = _task_run_identity(task_run_id)
    current = _current_time(now)
    if not isinstance(gateway, AgentGateway) or not callable(renew_lease):
        raise LearningCommandError(
            "learning.generation_runtime_invalid.v1",
            "题库生成运行器不合法。",
        )
    terminal = QuestionBankSeries.objects.filter(pk=identity).first()
    if terminal is None:
        raise LearningCommandError("learning.bank_not_found.v1", "题库不存在。")
    if terminal.state == QuestionBankSeriesState.PUBLISHED:
        _release_active(terminal)
        return _result(terminal)
    if terminal.state in {
        QuestionBankSeriesState.GENERATION_FAILED,
        QuestionBankSeriesState.DELETED,
    }:
        raise TaskCancelled(result_ref=f"question-generation:{identity}:terminal")
    try:
        _, blocks, estimated_tokens, source_units = _source(
            series_id=identity,
            storage=storage,
        )
    except LearningCommandError as error:
        if error.code == "learning.document_not_available.v1":
            mark_question_bank_generation_final_failed(
                series_id=identity,
                safe_error_code="learning.generation_source_unavailable.v1",
                completed_at=current,
                safe_summary="源知识文档已删除或不可用，题库生成已取消。",
            )
            raise TaskCancelled(
                result_ref=f"question-generation:{identity}:source"
            ) from None
        raise
    claim = _claim_generation_attempt(
        series_id=identity,
        task_run_id=stable_task_run_id,
        chunk_count=len(blocks),
        estimated_input_tokens=estimated_tokens,
        now=current,
    )
    renew_lease()
    reservation = None
    try:
        reservation = reserve_learning_model_run(
            account_id=claim.owner_id,
            kind=LearningModelRunKind.GENERATION,
            owner_ref=f"{identity}:{claim.attempt}",
            idempotency_key=f"generation-runtime:{identity}:{claim.attempt}",
            lease_expires_at=current + timedelta(hours=1),
            now=current,
        )
        batches = batch_source_knowledge_units(source_units)
        publications: list[QuestionBankPublicationDraft] = []
        last_invocation_id: str | None = None
        for batch_index, batch in enumerate(batches):
            if claim.attempt == 1 and batch_index == 0:
                invocation = bind_agent_invocation_task_run(
                    invocation_id=claim.snapshot_invocation_id,
                    task_run_id=stable_task_run_id,
                )
            else:
                invocation = create_agent_invocation_from_snapshot(
                    source_invocation_id=claim.snapshot_invocation_id,
                    caller_type="question_generation",
                    caller_id=f"{identity}:{claim.attempt}:{batch_index + 1}",
                    idempotency_key=(
                        f"generation:{identity}:{claim.attempt}:{batch_index + 1}"
                    ),
                    task_run_id=stable_task_run_id,
                )
            _record_runtime_ids(
                series_id=identity,
                task_run_id=stable_task_run_id,
                invocation_id=invocation.id,
                reservation_id=reservation.reservation_id,
            )
            source_ids = tuple(unit.logical_id for unit in batch)
            question_upper_bound = claim.max_questions_per_volume * 2
            generated = invoke_structured(
                gateway=gateway,
                invocation_id=invocation.id,
                input_blocks=(_source_batch_material(batch),),
                prompt_variables={
                    "knowledge_points": (
                        "这些是当前批次可引用的源条目 ID 白名单。它们只是证据片段，"
                        "不是预设知识点或题目；请自行判断知识点和题目数量，可以合并或拆分。"
                        "每个 knowledge_point 的 source_unit_ids 只能引用这些 ID："
                        + ",".join(source_ids)
                    ),
                    "question_types": ",".join(claim.allowed_question_types),
                    "question_limit": str(question_upper_bound),
                    "tag_candidates": _tag_candidates(),
                },
                output_validator=_publication_output_validator(
                    allowed_types=claim.allowed_question_types,
                    maximum_questions=question_upper_bound,
                    expected_source_unit_ids=source_ids,
                ),
                now=current,
                lease_seconds=3_600,
            )
            publications.append(
                question_bank_publication_draft(generated.validated_output.value)
            )
            last_invocation_id = generated.invocation_id
            renew_lease()
        publication = _merge_publications(
            publications=tuple(publications),
            units=source_units,
            maximum_questions_per_volume=claim.max_questions_per_volume,
        )
        release_learning_model_run(reservation_id=reservation.reservation_id)
        reservation = None
        published = publish_question_bank_generation(
            owner_id=claim.owner_id,
            series_id=identity,
            expected_series_version=claim.series_version,
            publication=publication,
            now=current,
        )
    except (AgentCommandError, GatewayError, LearningCommandError) as error:
        _record_retry_error(
            series_id=identity,
            task_run_id=stable_task_run_id,
            error_code=error.code,
        )
        if reservation is not None:
            release_learning_model_run(reservation_id=reservation.reservation_id)
        if error.code == "learning.document_not_available.v1":
            mark_question_bank_generation_final_failed(
                series_id=identity,
                safe_error_code="learning.generation_source_unavailable.v1",
                completed_at=current,
                safe_summary="源知识文档已删除或不可用，题库生成已取消。",
            )
            raise TaskCancelled(
                result_ref=f"question-generation:{identity}:source"
            ) from None
        if (
            isinstance(error, GatewayError)
            and not error.retryable
            and error.code not in _RETRYABLE_OUTPUT_ERRORS
        ):
            raise TaskFinalFailed(error_code=error.code) from None
        raise RetryableTaskError(error.code) from None
    except Exception:
        if reservation is not None:
            release_learning_model_run(reservation_id=reservation.reservation_id)
        raise
    return QuestionGenerationExecutionResult(
        series_id=identity,
        state=QuestionBankSeriesState.PUBLISHED,
        coverage_state=published.coverage_state,
        volume_count=published.volume_count,
        invocation_id=last_invocation_id,
    )


def mark_question_bank_generation_final_failed(
    *,
    series_id,
    safe_error_code: str,
    completed_at: datetime,
    safe_summary: str = "题库生成任务在三次尝试后仍未成功。",
) -> QuestionGenerationExecutionResult:
    identity = _series_identity(series_id)
    current = _current_time(completed_at)
    if (
        not isinstance(safe_error_code, str)
        or _SAFE_ERROR_CODE.fullmatch(safe_error_code) is None
        or not isinstance(safe_summary, str)
        or not 1 <= len(safe_summary.strip()) <= 500
    ):
        raise LearningCommandError(
            "learning.generation_result_invalid.v1",
            "题库生成失败结果不合法。",
        )
    try:
        candidate = QuestionBankSeries.objects.get(pk=identity)
    except QuestionBankSeries.DoesNotExist:
        raise LearningCommandError(
            "learning.bank_not_found.v1", "题库不存在。"
        ) from None
    if candidate.state == QuestionBankSeriesState.PUBLISHED:
        _release_active(candidate)
        return _result(candidate)
    if candidate.state == QuestionBankSeriesState.GENERATION_FAILED:
        _release_active(candidate)
        return _result(candidate)
    _release_active(candidate)
    with transaction.atomic():
        series = QuestionBankSeries.objects.select_for_update().get(pk=identity)
        if series.state == QuestionBankSeriesState.PUBLISHED:
            return _result(series)
        if series.state == QuestionBankSeriesState.GENERATION_FAILED:
            return _result(series)
        if series.state not in {
            QuestionBankSeriesState.GENERATION_PENDING,
            QuestionBankSeriesState.GENERATING,
        }:
            raise LearningCommandError(
                "learning.generation_conflict.v1", "题库生成状态冲突。"
            )
        series.state = QuestionBankSeriesState.GENERATION_FAILED
        series.started_at = series.started_at or current
        series.completed_at = current
        series.safe_reason_code = safe_error_code
        series.safe_summary = safe_summary.strip()
        series.last_error_code = safe_error_code
        series.failure_purge_after = current + timedelta(days=30)
        series.row_version += 1
        series.save()
        enqueue_event(
            GENERATION_FAILED,
            aggregate_type="question_bank_series",
            aggregate_id=str(series.id),
            payload={
                "recipient_id": str(series.owner_id),
                "error_code": safe_error_code,
            },
        )
    return _result(series)


__all__ = [
    "QuestionGenerationExecutionResult",
    "execute_question_bank_generation",
    "mark_question_bank_generation_final_failed",
]
