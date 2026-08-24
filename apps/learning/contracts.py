from dataclasses import dataclass
from enum import StrEnum

from django.db import models

DEFAULT_DAILY_UPLOADS = 10
DEFAULT_PENDING_REVIEWS = 3
DEFAULT_DAILY_GENERATIONS = 5
DEFAULT_CONCURRENT_MODEL_RUNS = 1
DEFAULT_UNPURGED_BANKS = 100

MIN_DAILY_UPLOADS = 1
MAX_DAILY_UPLOADS = 100
MIN_PENDING_REVIEWS = 1
MAX_PENDING_REVIEWS = 20
MIN_DAILY_GENERATIONS = 1
MAX_DAILY_GENERATIONS = 50
MIN_CONCURRENT_MODEL_RUNS = 1
MAX_CONCURRENT_MODEL_RUNS = 3
MIN_UNPURGED_BANKS = 1
MAX_UNPURGED_BANKS = 2_000
DEFAULT_API_MINUTE_LIMIT = 60
DEFAULT_API_DAILY_LIMIT = 3_000
MIN_API_MINUTE_LIMIT = 1
MAX_API_MINUTE_LIMIT = 600
MIN_API_DAILY_LIMIT = 100
MAX_API_DAILY_LIMIT = 100_000
MIN_QUESTIONS_PER_VOLUME = 1
MAX_QUESTIONS_PER_VOLUME = 2_000

CURRENT_UPLOAD_STATEMENT_VERSION = "knowledge-upload.v1"

LEARNING_ADMIN_REASON_CHOICES = (
    ("policy_review", "内容规范复核"),
    ("security_review", "安全风险复核"),
    ("legal_review", "法务合规复核"),
    ("quality_review", "内容质量复核"),
    ("duplicate_content", "重复内容处理"),
    ("admin_review", "其他管理复核"),
)
LEARNING_ADMIN_REASON_CODES = frozenset(
    value for value, _label in LEARNING_ADMIN_REASON_CHOICES
)


class KnowledgeDocumentState(models.TextChoices):
    STAGED = "STAGED", "Staged"
    REVIEW_PENDING = "REVIEW_PENDING", "Review pending"
    REVIEWING = "REVIEWING", "Reviewing"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    REVIEW_FAILED = "REVIEW_FAILED", "Review failed"
    DELETE_PENDING = "DELETE_PENDING", "Delete pending"
    CONTENT_PURGED = "CONTENT_PURGED", "Content purged"
    DELETED = "DELETED", "Deleted"


class KnowledgeReviewRunState(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"


class KnowledgeReviewOutcome(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class LearningModelRunKind(models.TextChoices):
    REVIEW = "REVIEW", "Review"
    GENERATION = "GENERATION", "Generation"


class LearningModelRunStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    RELEASED = "RELEASED", "Released"
    EXPIRED = "EXPIRED", "Expired"


class DocumentSubmissionOutcome(StrEnum):
    CREATED = "CREATED"
    IDEMPOTENT = "IDEMPOTENT"


class LearningCleanupOutcome(StrEnum):
    NOT_DUE = "NOT_DUE"
    RETAINED = "RETAINED"
    CONTENT_PURGED = "CONTENT_PURGED"
    DELETED = "DELETED"
    ALREADY_PURGED = "ALREADY_PURGED"


class LearningAppealState(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"


class LearningAppealDecision(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class LearningAdminTargetType(StrEnum):
    DOCUMENT = "DOCUMENT"
    QUESTION_BANK = "QUESTION_BANK"


class AdminLearningAction(StrEnum):
    HIDE = "HIDE"
    RESTORE = "RESTORE"
    DELETE = "DELETE"


class LearningDeletionActor(models.TextChoices):
    OWNER = "OWNER", "Owner"
    ADMINISTRATOR = "ADMIN", "Administrator"


class KnowledgeDocumentAccessPurpose(models.TextChoices):
    OWNER_VIEW = "OWNER_VIEW", "本人查看"
    ADMIN_REVIEW = "ADMIN_REVIEW", "管理复核"
    APPEAL_REVIEW = "APPEAL_REVIEW", "申诉处理"
    MODERATION = "MODERATION", "管理处置"


class QuestionType(models.TextChoices):
    SINGLE_CHOICE = "SINGLE_CHOICE", "单选"
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE", "多选"
    TRUE_FALSE = "TRUE_FALSE", "判断"
    SHORT_ANSWER = "SHORT_ANSWER", "简答"


class QuestionBankCoverageState(models.TextChoices):
    COMPLETE = "COMPLETE", "Complete"
    PARTIAL = "PARTIAL", "Partial"


class QuestionBankSeriesState(models.TextChoices):
    GENERATION_PENDING = "GENERATION_PENDING", "Generation pending"
    GENERATING = "GENERATING", "Generating"
    PUBLISHED = "PUBLISHED", "Published"
    GENERATION_FAILED = "GENERATION_FAILED", "Generation failed"
    DELETED = "DELETED", "Deleted"


class QuestionBankVisibility(models.TextChoices):
    CONFIGURING = "CONFIGURING", "Configuring"
    PUBLISHED = "PUBLISHED", "Published"
    OWNER_HIDDEN = "OWNER_HIDDEN", "Owner hidden"
    ADMIN_HIDDEN = "ADMIN_HIDDEN", "Admin hidden"
    DELETE_PENDING = "DELETE_PENDING", "Delete pending"
    DELETED = "DELETED", "Deleted"


class QuestionBankApiCorsMode(models.TextChoices):
    ALLOWLIST = "ALLOWLIST", "精确来源白名单"


class QuizAttemptStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "进行中"
    SUBMITTED = "SUBMITTED", "已提交"
    DELETE_PENDING = "DELETE_PENDING", "删除待处理"
    DELETED = "DELETED", "已删除"


class QuizAttemptSource(models.TextChoices):
    QUESTION_BANK = "QUESTION_BANK", "题库"
    WRONG_QUESTIONS = "WRONG_QUESTIONS", "错题本"


class QuizMasteryStatus(models.TextChoices):
    TO_REVIEW = "TO_REVIEW", "待复习"
    MASTERED = "MASTERED", "已掌握"


class QuizSelfAssessment(models.TextChoices):
    MASTERED = "MASTERED", "已掌握"
    NOT_MASTERED = "NOT_MASTERED", "未掌握"


QUIZ_DURATION_OPTIONS = (10, 20, 30, 60, 90, 120)


@dataclass(frozen=True, slots=True)
class GenerationQuestionTypes:
    single_choice: bool = False
    multiple_choice: bool = False
    true_false: bool = False
    short_answer: bool = False

    def enabled(self) -> tuple[str, ...]:
        values = (
            (QuestionType.SINGLE_CHOICE, self.single_choice),
            (QuestionType.MULTIPLE_CHOICE, self.multiple_choice),
            (QuestionType.TRUE_FALSE, self.true_false),
            (QuestionType.SHORT_ANSWER, self.short_answer),
        )
        return tuple(value for value, enabled in values if enabled is True)


@dataclass(frozen=True, slots=True)
class KnowledgePointDraft:
    logical_id: str
    title: str
    importance: int
    source_unit_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class QuestionOptionDraft:
    option_id: str
    text: str


@dataclass(frozen=True, slots=True)
class QuestionDraft:
    logical_id: str
    ordinal: int
    question_type: QuestionType | str
    stem_markdown: str
    options: tuple[QuestionOptionDraft, ...]
    correct_option_ids: tuple[str, ...]
    boolean_answer: bool | None
    reference_answer: str
    scoring_points: tuple[str, ...]
    explanation_markdown: str
    knowledge_point_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QuestionContentDraft:
    logical_id: str
    stem_markdown: str
    options: tuple[QuestionOptionDraft, ...]
    correct_option_ids: tuple[str, ...]
    boolean_answer: bool | None
    reference_answer: str
    scoring_points: tuple[str, ...]
    explanation_markdown: str


@dataclass(frozen=True, slots=True)
class VolumeDraft:
    volume_number: int
    questions: tuple[QuestionDraft, ...]


@dataclass(frozen=True, slots=True)
class QuestionBankPublicationDraft:
    knowledge_points: tuple[KnowledgePointDraft, ...]
    volumes: tuple[VolumeDraft, ...]
    omitted_knowledge_point_ids: tuple[str, ...]
    tag_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LearningQuotaLimits:
    daily_uploads: int
    pending_reviews: int
    daily_generations: int
    concurrent_model_runs: int
    unpurged_banks: int


@dataclass(frozen=True, slots=True)
class LearningQuotaOverride:
    daily_uploads: int | None = None
    pending_reviews: int | None = None
    daily_generations: int | None = None
    concurrent_model_runs: int | None = None
    unpurged_banks: int | None = None


class LearningCommandError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        document_id=None,
    ) -> None:
        self.code = code
        self.safe_message = message
        self.document_id = document_id
        super().__init__(message)
