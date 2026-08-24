from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.learning.contracts import (
    KnowledgeReviewRunState,
    LearningCommandError,
    QuestionBankSeriesState,
)
from apps.learning.models import KnowledgeReviewRun, QuestionBankSeries

ReviewDispatcher = Callable[[str], None]
GenerationDispatcher = Callable[[str], None]


def _current_time(now: datetime | None) -> datetime:
    current = now or timezone.now()
    if not isinstance(current, datetime) or not timezone.is_aware(current):
        raise LearningCommandError("learning.time_invalid.v1", "审核派发时间不合法。")
    return current


def dispatch_knowledge_review_run(
    review_run_id: UUID,
    *,
    dispatcher: ReviewDispatcher,
    now: datetime | None = None,
) -> bool:
    if not isinstance(review_run_id, UUID) or not callable(dispatcher):
        raise LearningCommandError(
            "learning.review_dispatch_invalid.v1", "审核任务派发信息不合法。"
        )
    current = _current_time(now)
    with transaction.atomic():
        run = (
            KnowledgeReviewRun.objects.select_for_update()
            .filter(
                pk=review_run_id,
                state=KnowledgeReviewRunState.PENDING,
            )
            .first()
        )
        if run is None or not run.dispatch_required:
            return False
        try:
            dispatcher(str(review_run_id))
        except Exception:
            run.dispatch_attempted_at = current
            run.dispatched_at = None
            run.save(
                update_fields=(
                    "dispatch_attempted_at",
                    "dispatched_at",
                    "updated_at",
                )
            )
            return False
        run.dispatch_required = False
        run.dispatch_attempted_at = current
        run.dispatched_at = current
        run.save(
            update_fields=(
                "dispatch_required",
                "dispatch_attempted_at",
                "dispatched_at",
                "updated_at",
            )
        )
        return True


def dispatch_pending_knowledge_reviews(
    *,
    batch_size: int,
    dispatcher: ReviewDispatcher,
    now: datetime | None = None,
) -> tuple[UUID, ...]:
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= 100
        or not callable(dispatcher)
    ):
        raise LearningCommandError(
            "learning.review_dispatch_invalid.v1", "审核补偿派发信息不合法。"
        )
    current = _current_time(now)
    with transaction.atomic():
        identities = tuple(
            KnowledgeReviewRun.objects.select_for_update(skip_locked=True)
            .filter(
                state=KnowledgeReviewRunState.PENDING,
                dispatch_required=True,
            )
            .order_by("created_at", "id")
            .values_list("id", flat=True)[:batch_size]
        )
    dispatched = []
    for identity in identities:
        if dispatch_knowledge_review_run(
            identity,
            dispatcher=dispatcher,
            now=current,
        ):
            dispatched.append(identity)
    return tuple(dispatched)


def dispatch_question_bank_generation(
    series_id: UUID,
    *,
    dispatcher: GenerationDispatcher,
    now: datetime | None = None,
) -> bool:
    if not isinstance(series_id, UUID) or not callable(dispatcher):
        raise LearningCommandError(
            "learning.generation_dispatch_invalid.v1",
            "题库生成任务派发信息不合法。",
        )
    current = _current_time(now)
    with transaction.atomic():
        series = (
            QuestionBankSeries.objects.select_for_update()
            .filter(pk=series_id, state=QuestionBankSeriesState.GENERATION_PENDING)
            .first()
        )
        if series is None or not series.dispatch_required:
            return False
        try:
            dispatcher(str(series_id))
        except Exception:
            series.dispatch_attempted_at = current
            series.dispatched_at = None
            series.save(
                update_fields=(
                    "dispatch_attempted_at",
                    "dispatched_at",
                    "updated_at",
                )
            )
            return False
        series.dispatch_required = False
        series.dispatch_attempted_at = current
        series.dispatched_at = current
        series.save(
            update_fields=(
                "dispatch_required",
                "dispatch_attempted_at",
                "dispatched_at",
                "updated_at",
            )
        )
        return True


def dispatch_pending_question_bank_generations(
    *,
    batch_size: int,
    dispatcher: GenerationDispatcher,
    now: datetime | None = None,
) -> tuple[UUID, ...]:
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= 100
        or not callable(dispatcher)
    ):
        raise LearningCommandError(
            "learning.generation_dispatch_invalid.v1",
            "题库生成补偿派发信息不合法。",
        )
    current = _current_time(now)
    with transaction.atomic():
        identities = tuple(
            QuestionBankSeries.objects.select_for_update(skip_locked=True)
            .filter(
                state=QuestionBankSeriesState.GENERATION_PENDING,
                dispatch_required=True,
            )
            .order_by("created_at", "id")
            .values_list("id", flat=True)[:batch_size]
        )
    dispatched = []
    for identity in identities:
        if dispatch_question_bank_generation(
            identity,
            dispatcher=dispatcher,
            now=current,
        ):
            dispatched.append(identity)
    return tuple(dispatched)


__all__ = [
    "GenerationDispatcher",
    "ReviewDispatcher",
    "dispatch_knowledge_review_run",
    "dispatch_pending_knowledge_reviews",
    "dispatch_pending_question_bank_generations",
    "dispatch_question_bank_generation",
]
