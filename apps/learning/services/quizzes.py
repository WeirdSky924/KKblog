import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.accounts.public import is_active_account, lock_active_account
from apps.learning.contracts import (
    QUIZ_DURATION_OPTIONS,
    QUIZ_QUESTION_TYPE_ORDER,
    LearningCommandError,
    QuestionType,
    QuizAttemptMode,
    QuizAttemptSource,
    QuizAttemptStatus,
    QuizSelfAssessment,
)
from apps.learning.models import QuestionBank, QuizAttempt, QuizResponse, WrongQuestion


@dataclass(frozen=True, slots=True)
class QuizStartResult:
    attempt_id: UUID
    response_ids: tuple[UUID, ...]
    question_count: int
    row_version: int


@dataclass(frozen=True, slots=True)
class QuizResponseResult:
    response_id: UUID
    row_version: int
    saved_at: datetime


@dataclass(frozen=True, slots=True)
class QuizResponseSubmitResult:
    response_id: UUID
    row_version: int
    submitted_at: datetime
    is_correct: bool | None


@dataclass(frozen=True, slots=True)
class QuizAssessmentResult:
    response_id: UUID
    self_assessment: str
    row_version: int
    attempt_row_version: int


@dataclass(frozen=True, slots=True)
class QuizSubmitResult:
    attempt_id: UUID
    objective_score: int
    objective_total: int
    short_answer_mastered: int
    short_answer_total: int
    submitted_at: datetime
    row_version: int


def _owner(account_id):
    if not isinstance(account_id, UUID) or not is_active_account(account_id):
        raise LearningCommandError("learning.quiz_login_required.v1", "请先登录。")
    return account_id


def _lock_account(account_id: UUID) -> None:
    if not lock_active_account(account_id):
        raise LearningCommandError("learning.quiz_login_required.v1", "请先登录。")


def _current_time(value: datetime | None) -> datetime:
    current = value or timezone.now()
    if not isinstance(current, datetime) or current.tzinfo is None:
        raise LearningCommandError("learning.quiz_time_invalid.v1", "答题时间不合法。")
    return current


def _select_questions(questions, *, question_count: int, random_questions: bool):
    """Select the requested questions, then order them by type.

    Random selection remains global so the configured question count keeps its
    existing semantics. Once selected, questions are grouped in the product
    order and shuffled only within their own type when randomization is on.
    """
    randomizer = secrets.SystemRandom() if random_questions else None
    selected = (
        randomizer.sample(questions, question_count)
        if randomizer is not None
        else questions[:question_count]
    )
    grouped = {question_type: [] for question_type in QUIZ_QUESTION_TYPE_ORDER}
    for question in selected:
        grouped[question.question_type].append(question)
    if randomizer is not None:
        for group in grouped.values():
            randomizer.shuffle(group)
    return [
        question
        for question_type in QUIZ_QUESTION_TYPE_ORDER
        for question in grouped[question_type]
    ]


def _question_types(values) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise LearningCommandError(
            "learning.quiz_config_invalid.v1", "题型选择不合法。"
        )
    try:
        normalized = tuple(dict.fromkeys(QuestionType(value).value for value in values))
    except (TypeError, ValueError):
        raise LearningCommandError(
            "learning.quiz_config_invalid.v1", "题型选择不合法。"
        ) from None
    if not normalized:
        raise LearningCommandError(
            "learning.quiz_config_invalid.v1", "至少选择一种题型。"
        )
    return normalized


def _duration(timed: bool, duration_minutes) -> int | None:
    if not isinstance(timed, bool):
        raise LearningCommandError(
            "learning.quiz_config_invalid.v1", "计时配置不合法。"
        )
    if not timed:
        if duration_minutes not in (None, "", 0):
            raise LearningCommandError(
                "learning.quiz_config_invalid.v1", "计时配置不合法。"
            )
        return None
    if duration_minutes not in QUIZ_DURATION_OPTIONS:
        raise LearningCommandError(
            "learning.quiz_config_invalid.v1", "答题时长不合法。"
        )
    return duration_minutes


def _mode(value: str) -> QuizAttemptMode:
    try:
        return QuizAttemptMode(value)
    except (TypeError, ValueError):
        raise LearningCommandError(
            "learning.quiz_config_invalid.v1", "答题模式不合法。"
        ) from None


def _answer(value, response: QuizResponse):
    question_type = response.question_type
    if question_type in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE):
        if not isinstance(value, (list, tuple)) or any(
            not isinstance(item, str) for item in value
        ):
            raise LearningCommandError(
                "learning.quiz_answer_invalid.v1", "答案格式不合法。"
            )
        selected = list(dict.fromkeys(value))
        option_ids = {str(option["id"]) for option in response.options}
        if any(item not in option_ids for item in selected) or (
            question_type == QuestionType.SINGLE_CHOICE and len(selected) > 1
        ):
            raise LearningCommandError(
                "learning.quiz_answer_invalid.v1", "答案格式不合法。"
            )
        return selected
    if question_type == QuestionType.TRUE_FALSE:
        if value is None:
            return None
        if not isinstance(value, bool):
            raise LearningCommandError(
                "learning.quiz_answer_invalid.v1", "答案格式不合法。"
            )
        return value
    if not isinstance(value, str) or len(value) > 10_000:
        raise LearningCommandError(
            "learning.quiz_answer_invalid.v1", "答案格式不合法。"
        )
    return value


def start_quiz_attempt(
    *,
    account_id,
    bank_id,
    expected_revision_id,
    question_types,
    question_count: int,
    timed: bool = False,
    duration_minutes=None,
    random_questions: bool = True,
    random_options: bool = True,
    source: str = QuizAttemptSource.QUESTION_BANK,
    mode: str = QuizAttemptMode.EXAM,
    now: datetime | None = None,
) -> QuizStartResult:
    account_id = _owner(account_id)
    selected_types = _question_types(question_types)
    duration = _duration(timed, duration_minutes)
    selected_mode = _mode(mode)
    if (
        not isinstance(question_count, int)
        or isinstance(question_count, bool)
        or question_count < 1
        or not isinstance(random_questions, bool)
        or not isinstance(random_options, bool)
        or source != QuizAttemptSource.QUESTION_BANK
    ):
        raise LearningCommandError(
            "learning.quiz_config_invalid.v1", "答题配置不合法。"
        )
    started = _current_time(now)
    with transaction.atomic():
        _lock_account(account_id)
        try:
            bank = (
                QuestionBank.objects.select_for_update(of=("self",))
                .select_related("series__owner", "current_revision")
                .get(pk=bank_id, visibility="PUBLISHED")
            )
        except (QuestionBank.DoesNotExist, TypeError, ValueError):
            raise LearningCommandError(
                "learning.bank_not_public.v1", "题库暂不可用。"
            ) from None
        revision = bank.current_revision
        if revision is None:
            raise LearningCommandError("learning.bank_not_public.v1", "题库暂不可用。")
        if (
            not isinstance(expected_revision_id, UUID)
            or revision.id != expected_revision_id
        ):
            raise LearningCommandError(
                "learning.quiz_config_conflict.v1", "题库内容已更新，请重新确认配置。"
            )
        questions = list(
            revision.questions.filter(question_type__in=selected_types).order_by(
                "ordinal"
            )
        )
        if question_count > len(questions):
            raise LearningCommandError(
                "learning.quiz_count_invalid.v1", "题量超过所选题型范围。"
            )
        selected = _select_questions(
            questions,
            question_count=question_count,
            random_questions=random_questions,
        )
        question_order = [question.logical_id for question in selected]
        option_orders = {}
        response_specs = []
        for question in selected:
            options = list(question.options)
            option_ids = [str(option["id"]) for option in options]
            if random_options and question.question_type in (
                QuestionType.SINGLE_CHOICE,
                QuestionType.MULTIPLE_CHOICE,
            ):
                secrets.SystemRandom().shuffle(options)
                option_ids = [str(option["id"]) for option in options]
            option_orders[question.logical_id] = option_ids
            response_specs.append((question, options))
        owner = bank.series.owner
        owner_display_name = owner.nickname or owner.email.partition("@")[0]
        attempt = QuizAttempt.objects.create(
            account_id=account_id,
            bank=bank,
            revision=revision,
            source=QuizAttemptSource.QUESTION_BANK,
            mode=selected_mode,
            bank_id_snapshot=bank.id,
            series_id_snapshot=bank.series_id,
            revision_id_snapshot=revision.id,
            owner_id_snapshot=owner.id,
            bank_title=bank.series.base_title,
            owner_display_name=owner_display_name,
            selected_question_types=list(selected_types),
            question_count=question_count,
            timed=timed,
            duration_minutes=duration,
            deadline_at=started + timedelta(minutes=duration) if duration else None,
            random_questions=random_questions,
            random_options=random_options,
            question_order=question_order,
            option_orders=option_orders,
            started_at=started,
        )
        response_ids = []
        for question, options in response_specs:
            response = QuizResponse.objects.create(
                attempt=attempt,
                question=question,
                logical_id=question.logical_id,
                ordinal=question.ordinal,
                question_type=question.question_type,
                stem_markdown=question.stem_markdown,
                options=options,
                correct_option_ids=list(question.correct_option_ids),
                boolean_answer=question.boolean_answer,
                reference_answer=question.reference_answer,
                scoring_points=list(question.scoring_points),
                explanation_markdown=question.explanation_markdown,
            )
            response_ids.append(response.id)
    return QuizStartResult(
        attempt.id, tuple(response_ids), question_count, attempt.row_version
    )


def start_wrong_question_attempt(
    *,
    account_id,
    bank_id,
    expected_revision_id,
    expected_source_keys,
    question_types,
    question_count: int,
    timed: bool = False,
    duration_minutes=None,
    random_questions: bool = True,
    random_options: bool = True,
    mode: str = QuizAttemptMode.EXAM,
    now: datetime | None = None,
) -> QuizStartResult:
    account_id = _owner(account_id)
    selected_types = _question_types(question_types)
    duration = _duration(timed, duration_minutes)
    selected_mode = _mode(mode)
    if (
        not isinstance(question_count, int)
        or isinstance(question_count, bool)
        or question_count < 1
        or not isinstance(random_questions, bool)
        or not isinstance(random_options, bool)
        or not isinstance(expected_source_keys, (list, tuple))
        or any(not isinstance(item, str) for item in expected_source_keys)
    ):
        raise LearningCommandError(
            "learning.quiz_config_invalid.v1", "答题配置不合法。"
        )
    started = _current_time(now)
    with transaction.atomic():
        _lock_account(account_id)
        try:
            bank = (
                QuestionBank.objects.select_for_update(of=("self",))
                .select_related("series__owner", "current_revision")
                .get(pk=bank_id, visibility="PUBLISHED")
            )
        except (QuestionBank.DoesNotExist, TypeError, ValueError):
            raise LearningCommandError(
                "learning.bank_not_public.v1", "题库暂不可用。"
            ) from None
        revision = bank.current_revision
        if (
            revision is None
            or not isinstance(expected_revision_id, UUID)
            or revision.id != expected_revision_id
        ):
            raise LearningCommandError(
                "learning.quiz_config_conflict.v1", "题库内容已更新，请重新确认配置。"
            )
        all_wrong_items = list(
            WrongQuestion.objects.select_for_update()
            .filter(
                account_id=account_id,
                bank_id=bank.id,
                mastery_status="TO_REVIEW",
                question_id__isnull=False,
            )
            .order_by("source_key")
        )
        actual_source_keys = tuple(item.source_key for item in all_wrong_items)
        if tuple(expected_source_keys) != actual_source_keys:
            raise LearningCommandError(
                "learning.quiz_config_conflict.v1", "错题集合已更新，请重新确认配置。"
            )
        wrong_items = [
            item for item in all_wrong_items if item.question_type in selected_types
        ]
        if question_count > len(wrong_items):
            raise LearningCommandError(
                "learning.quiz_count_invalid.v1", "题量超过所选错题范围。"
            )
        selected = _select_questions(
            wrong_items,
            question_count=question_count,
            random_questions=random_questions,
        )
        question_order = [item.logical_id for item in selected]
        option_orders = {}
        response_specs = []
        for ordinal, item in enumerate(selected, start=1):
            options = list(item.options)
            if random_options and item.question_type in (
                QuestionType.SINGLE_CHOICE,
                QuestionType.MULTIPLE_CHOICE,
            ):
                secrets.SystemRandom().shuffle(options)
            option_orders[item.logical_id] = [str(option["id"]) for option in options]
            response_specs.append((ordinal, item, options))
        owner = bank.series.owner
        owner_display_name = owner.nickname or owner.email.partition("@")[0]
        attempt = QuizAttempt.objects.create(
            account_id=account_id,
            bank=bank,
            revision=revision,
            source=QuizAttemptSource.WRONG_QUESTIONS,
            mode=selected_mode,
            bank_id_snapshot=bank.id,
            series_id_snapshot=bank.series_id,
            revision_id_snapshot=revision.id,
            owner_id_snapshot=owner.id,
            bank_title=bank.series.base_title,
            owner_display_name=owner_display_name,
            selected_question_types=list(selected_types),
            question_count=question_count,
            timed=timed,
            duration_minutes=duration,
            deadline_at=started + timedelta(minutes=duration) if duration else None,
            random_questions=random_questions,
            random_options=random_options,
            question_order=question_order,
            option_orders=option_orders,
            started_at=started,
        )
        response_ids = []
        for ordinal, item, options in response_specs:
            response = QuizResponse.objects.create(
                attempt=attempt,
                question=item.question,
                logical_id=item.logical_id,
                ordinal=ordinal,
                question_type=item.question_type,
                stem_markdown=item.stem_markdown,
                options=options,
                correct_option_ids=list(item.correct_option_ids),
                boolean_answer=item.boolean_answer,
                reference_answer=item.reference_answer,
                scoring_points=list(item.scoring_points),
                explanation_markdown=item.explanation_markdown,
            )
            response_ids.append(response.id)
    return QuizStartResult(
        attempt.id, tuple(response_ids), question_count, attempt.row_version
    )


def save_quiz_response(
    *,
    account_id,
    attempt_id,
    response_id,
    expected_version: int,
    request_id: str,
    answer,
    now: datetime | None = None,
) -> QuizResponseResult:
    account_id = _owner(account_id)
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
        raise LearningCommandError(
            "learning.quiz_request_invalid.v1", "请求标识不合法。"
        )
    with transaction.atomic():
        try:
            attempt = QuizAttempt.objects.select_for_update().get(
                pk=attempt_id, account_id=account_id
            )
            response = QuizResponse.objects.select_for_update().get(
                pk=response_id, attempt=attempt
            )
        except (
            QuizAttempt.DoesNotExist,
            QuizResponse.DoesNotExist,
            TypeError,
            ValueError,
        ):
            raise LearningCommandError(
                "learning.quiz_not_found.v1", "答题记录不存在。"
            ) from None
        if attempt.status != QuizAttemptStatus.IN_PROGRESS:
            raise LearningCommandError(
                "learning.quiz_closed.v1", "答题已提交，不能继续修改。"
            )
        if response.submitted_at is not None:
            raise LearningCommandError(
                "learning.quiz_closed.v1", "本题已提交，不能继续修改。"
            )
        if response.last_save_request_id == request_id:
            saved_at = response.saved_at or _current_time(now)
            return QuizResponseResult(response.id, response.row_version, saved_at)
        if response.row_version != expected_version:
            raise LearningCommandError(
                "learning.quiz_response_conflict.v1", "答案已在其他设备更新。"
            )
        response.answer = _answer(answer, response)
        saved_at = _current_time(now)
        response.saved_at = saved_at
        response.last_save_request_id = request_id
        response.row_version += 1
        response.save(
            update_fields=(
                "answer",
                "saved_at",
                "last_save_request_id",
                "row_version",
            )
        )
    return QuizResponseResult(response.id, response.row_version, saved_at)


def _is_correct(response: QuizResponse) -> bool:
    if response.answer is None:
        return False
    if response.question_type == QuestionType.TRUE_FALSE:
        return response.answer is response.boolean_answer
    if response.question_type == QuestionType.SINGLE_CHOICE:
        return set(response.answer) == set(response.correct_option_ids)
    if response.question_type == QuestionType.MULTIPLE_CHOICE:
        return set(response.answer) == set(response.correct_option_ids)
    return False


def submit_quiz_response(
    *,
    account_id,
    attempt_id,
    response_id,
    expected_version: int,
    request_id: str,
    answer,
    now: datetime | None = None,
) -> QuizResponseSubmitResult:
    account_id = _owner(account_id)
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
        raise LearningCommandError(
            "learning.quiz_request_invalid.v1", "请求标识不合法。"
        )
    if (
        not isinstance(expected_version, int)
        or isinstance(expected_version, bool)
        or expected_version < 1
    ):
        raise LearningCommandError(
            "learning.quiz_response_conflict.v1", "答案版本已更新，请刷新后重试。"
        )
    submitted_at = _current_time(now)
    with transaction.atomic():
        _lock_account(account_id)
        try:
            attempt = QuizAttempt.objects.select_for_update().get(
                pk=attempt_id, account_id=account_id
            )
            response = QuizResponse.objects.select_for_update().get(
                pk=response_id, attempt=attempt
            )
        except (
            QuizAttempt.DoesNotExist,
            QuizResponse.DoesNotExist,
            TypeError,
            ValueError,
        ):
            raise LearningCommandError(
                "learning.quiz_not_found.v1", "答题记录不存在。"
            ) from None
        if attempt.mode != QuizAttemptMode.PRACTICE:
            raise LearningCommandError(
                "learning.quiz_mode_invalid.v1", "当前答题模式不支持逐题提交。"
            )
        if response.submitted_at is not None:
            return QuizResponseSubmitResult(
                response.id,
                response.row_version,
                response.submitted_at,
                response.is_correct,
            )
        if attempt.status != QuizAttemptStatus.IN_PROGRESS:
            raise LearningCommandError(
                "learning.quiz_closed.v1", "答题已提交，不能继续修改。"
            )
        if response.row_version != expected_version:
            raise LearningCommandError(
                "learning.quiz_response_conflict.v1", "答案已在其他设备更新。"
            )
        response.answer = _answer(answer, response)
        response.is_correct = (
            _is_correct(response)
            if response.question_type != QuestionType.SHORT_ANSWER
            else None
        )
        response.score = (
            int(response.is_correct)
            if response.question_type != QuestionType.SHORT_ANSWER
            else None
        )
        response.saved_at = submitted_at
        response.submitted_at = submitted_at
        response.row_version += 1
        response.save(
            update_fields=(
                "answer",
                "is_correct",
                "score",
                "saved_at",
                "submitted_at",
                "row_version",
            )
        )
        if response.question_type != QuestionType.SHORT_ANSWER:
            _upsert_wrong(
                attempt,
                response,
                correct=bool(response.is_correct),
                now=submitted_at,
            )
    return QuizResponseSubmitResult(
        response.id,
        response.row_version,
        submitted_at,
        response.is_correct,
    )


def _upsert_wrong(
    attempt: QuizAttempt, response: QuizResponse, *, correct: bool, now: datetime
):
    source_key = f"{attempt.bank_id_snapshot}:{response.logical_id}"
    wrong = (
        WrongQuestion.objects.select_for_update()
        .filter(account_id=attempt.account_id, source_key=source_key)
        .first()
    )
    if wrong is None:
        if correct:
            return
        WrongQuestion.objects.create(
            account_id=attempt.account_id,
            bank=attempt.bank,
            question=response.question,
            source_key=source_key,
            bank_title=attempt.bank_title,
            owner_display_name=attempt.owner_display_name,
            logical_id=response.logical_id,
            question_type=response.question_type,
            stem_markdown=response.stem_markdown,
            options=response.options,
            correct_option_ids=response.correct_option_ids,
            boolean_answer=response.boolean_answer,
            reference_answer=response.reference_answer,
            scoring_points=response.scoring_points,
            explanation_markdown=response.explanation_markdown,
            first_wrong_at=now,
            last_wrong_at=now,
            status_changed_at=now,
        )
        return
    if correct:
        wrong.correct_count += 1
        wrong.last_correct_at = now
    else:
        wrong.wrong_count += 1
        wrong.last_wrong_at = now
    wrong.row_version += 1
    wrong.save(
        update_fields=(
            "correct_count",
            "last_correct_at",
            "wrong_count",
            "last_wrong_at",
            "row_version",
        )
    )


def submit_quiz_attempt(
    *, account_id, attempt_id, request_id: str, now: datetime | None = None
) -> QuizSubmitResult:
    account_id = _owner(account_id)
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
        raise LearningCommandError(
            "learning.quiz_request_invalid.v1", "请求标识不合法。"
        )
    submitted_at = _current_time(now)
    with transaction.atomic():
        _lock_account(account_id)
        try:
            attempt = QuizAttempt.objects.select_for_update().get(
                pk=attempt_id, account_id=account_id
            )
        except (QuizAttempt.DoesNotExist, TypeError, ValueError):
            raise LearningCommandError(
                "learning.quiz_not_found.v1", "答题记录不存在。"
            ) from None
        if attempt.status == QuizAttemptStatus.SUBMITTED:
            return QuizSubmitResult(
                attempt.id,
                attempt.objective_score or 0,
                attempt.objective_total or 0,
                attempt.short_answer_mastered or 0,
                attempt.short_answer_total or 0,
                attempt.submitted_at or submitted_at,
                attempt.row_version,
            )
        if attempt.status != QuizAttemptStatus.IN_PROGRESS:
            raise LearningCommandError("learning.quiz_closed.v1", "答题不能提交。")
        responses = list(attempt.responses.select_for_update().order_by("ordinal"))
        objective = [
            item
            for item in responses
            if item.question_type != QuestionType.SHORT_ANSWER
        ]
        short = [
            item
            for item in responses
            if item.question_type == QuestionType.SHORT_ANSWER
        ]
        objective_score = 0
        for response in responses:
            already_individually_submitted = response.submitted_at is not None
            correct = _is_correct(response)
            if response.question_type != QuestionType.SHORT_ANSWER:
                objective_score += int(correct)
                if not already_individually_submitted:
                    _upsert_wrong(attempt, response, correct=correct, now=submitted_at)
            if already_individually_submitted:
                continue
            response.is_correct = (
                correct if response.question_type != QuestionType.SHORT_ANSWER else None
            )
            response.score = (
                int(correct)
                if response.question_type != QuestionType.SHORT_ANSWER
                else None
            )
            response.submitted_at = submitted_at
            response.row_version += 1
            response.save(
                update_fields=("is_correct", "score", "submitted_at", "row_version")
            )
        short_mastered = sum(
            item.self_assessment == QuizSelfAssessment.MASTERED for item in short
        )
        attempt.status = QuizAttemptStatus.SUBMITTED
        attempt.objective_score = objective_score
        attempt.objective_total = len(objective)
        attempt.short_answer_mastered = short_mastered
        attempt.short_answer_total = len(short)
        attempt.actual_duration_seconds = max(
            0, int((submitted_at - attempt.started_at).total_seconds())
        )
        attempt.submit_request_id = request_id
        attempt.submitted_at = submitted_at
        attempt.row_version += 1
        attempt.save(
            update_fields=(
                "status",
                "objective_score",
                "objective_total",
                "short_answer_mastered",
                "short_answer_total",
                "actual_duration_seconds",
                "submit_request_id",
                "submitted_at",
                "row_version",
                "updated_at",
            )
        )
        if attempt.bank_id is not None:
            QuestionBank.objects.filter(pk=attempt.bank_id).update(
                completed_attempt_count=F("completed_attempt_count") + 1
            )
    return QuizSubmitResult(
        attempt.id,
        objective_score,
        len(objective),
        short_mastered,
        len(short),
        submitted_at,
        attempt.row_version,
    )


def assess_quiz_short_answer(
    *,
    account_id,
    attempt_id,
    response_id,
    expected_version: int,
    request_id: str,
    self_assessment,
    now: datetime | None = None,
) -> QuizAssessmentResult:
    account_id = _owner(account_id)
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
        raise LearningCommandError(
            "learning.quiz_request_invalid.v1", "请求标识不合法。"
        )
    try:
        assessment = QuizSelfAssessment(self_assessment)
    except (TypeError, ValueError):
        raise LearningCommandError(
            "learning.quiz_answer_invalid.v1", "掌握状态不合法。"
        ) from None
    assessed_at = _current_time(now)
    with transaction.atomic():
        _lock_account(account_id)
        try:
            attempt = QuizAttempt.objects.select_for_update().get(
                pk=attempt_id, account_id=account_id
            )
            response = QuizResponse.objects.select_for_update().get(
                pk=response_id,
                attempt=attempt,
                question_type=QuestionType.SHORT_ANSWER,
            )
        except (
            QuizAttempt.DoesNotExist,
            QuizResponse.DoesNotExist,
            TypeError,
            ValueError,
        ):
            raise LearningCommandError(
                "learning.quiz_not_found.v1", "答题记录不存在。"
            ) from None
        if response.assessment_request_id == request_id:
            return QuizAssessmentResult(
                response.id,
                response.self_assessment or assessment,
                response.row_version,
                attempt.row_version,
            )
        can_assess = (
            attempt.status == QuizAttemptStatus.SUBMITTED
            if attempt.mode == QuizAttemptMode.EXAM
            else response.submitted_at is not None
            and attempt.status
            in (QuizAttemptStatus.IN_PROGRESS, QuizAttemptStatus.SUBMITTED)
        )
        if not can_assess:
            raise LearningCommandError(
                "learning.quiz_closed.v1", "请先提交本题后再进行自评。"
            )
        if response.row_version != expected_version:
            raise LearningCommandError(
                "learning.quiz_response_conflict.v1", "答案已在其他设备更新。"
            )
        if response.self_assessment is not None:
            raise LearningCommandError(
                "learning.quiz_response_conflict.v1", "简答掌握状态已经提交。"
            )
        response.self_assessment = assessment
        response.assessment_request_id = request_id
        response.row_version += 1
        response.save(
            update_fields=(
                "self_assessment",
                "assessment_request_id",
                "row_version",
            )
        )
        mastered = assessment == QuizSelfAssessment.MASTERED
        _upsert_wrong(attempt, response, correct=mastered, now=assessed_at)
        if mastered and attempt.status == QuizAttemptStatus.SUBMITTED:
            attempt.short_answer_mastered = (attempt.short_answer_mastered or 0) + 1
        if attempt.status == QuizAttemptStatus.SUBMITTED:
            attempt.row_version += 1
            attempt.save(
                update_fields=(
                    "short_answer_mastered",
                    "row_version",
                    "updated_at",
                )
            )
    return QuizAssessmentResult(
        response.id,
        assessment,
        response.row_version,
        attempt.row_version,
    )


__all__ = [
    "QuizAssessmentResult",
    "QuizResponseResult",
    "QuizStartResult",
    "QuizSubmitResult",
    "assess_quiz_short_answer",
    "save_quiz_response",
    "start_quiz_attempt",
    "start_wrong_question_attempt",
    "submit_quiz_attempt",
]
