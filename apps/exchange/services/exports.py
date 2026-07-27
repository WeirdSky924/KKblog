from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.ids import normalize_ulid

from ..models import ExportJob, ExportSelection

AdministratorCheck = Callable[[UUID], bool]
SelectionProvider = Callable[..., Iterable[object]]
AuditWriter = Callable[..., object]
ExportDispatcher = Callable[[str], object]


class ExportScope(StrEnum):
    ALL = "ALL"
    AUTHOR = "AUTHOR"
    SECTION = "SECTION"
    ARTICLES = "ARTICLES"


class ExportRequestError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


@dataclass(frozen=True, slots=True)
class ExportRequestResult:
    job_id: str
    state: str
    selected_count: int


@dataclass(frozen=True, slots=True)
class _SelectionSnapshot:
    article_id: str
    author_id: UUID
    publication_state: str
    visibility: str
    section_id: UUID | None
    revision_ids: tuple[str, ...]
    working_revision_id: str | None
    published_revision_id: str | None
    scheduled_revision_id: str | None
    scheduled_for: datetime | None
    published_at: datetime | None
    deleted_at: datetime | None
    purge_after: datetime | None


def _uuid(value, *, code: str, message: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ExportRequestError(code, message) from None


def _optional_uuid(value, *, code: str) -> UUID | None:
    if value is None:
        return None
    return _uuid(value, code=code, message="导出范围无效。")


def _scope(value: str) -> ExportScope:
    try:
        return ExportScope(value)
    except (TypeError, ValueError):
        raise ExportRequestError(
            "exchange.export_scope_invalid.v1", "导出范围无效。"
        ) from None


def _article_ids(values) -> tuple[str, ...]:
    if values is None or isinstance(values, str | bytes):
        raise ExportRequestError(
            "exchange.export_scope_invalid.v1", "导出文章选择无效。"
        )
    try:
        return tuple(dict.fromkeys(normalize_ulid(value) for value in values))
    except (TypeError, ValueError):
        raise ExportRequestError(
            "exchange.export_scope_invalid.v1", "导出文章选择无效。"
        ) from None


def _scope_inputs(
    *, scope: ExportScope, author_id, section_id, article_ids
) -> tuple[UUID | None, UUID | None, tuple[str, ...]]:
    author = _optional_uuid(author_id, code="exchange.export_scope_invalid.v1")
    section = _optional_uuid(section_id, code="exchange.export_scope_invalid.v1")
    articles = _article_ids(article_ids)
    valid = (
        scope == ExportScope.ALL
        and author is None
        and section is None
        and not articles
        or scope == ExportScope.AUTHOR
        and author is not None
        and section is None
        and not articles
        or scope == ExportScope.SECTION
        and author is None
        and section is not None
        and not articles
        or scope == ExportScope.ARTICLES
        and author is None
        and section is None
        and bool(articles)
    )
    if not valid:
        raise ExportRequestError(
            "exchange.export_scope_invalid.v1", "导出范围与筛选条件不匹配。"
        )
    return author, section, articles


def _optional_ulid(value) -> str | None:
    if value is None:
        return None
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ExportRequestError(
            "exchange.export_snapshot_invalid.v1", "导出选择快照无效。"
        ) from None


def _snapshot(value: object) -> _SelectionSnapshot:
    try:
        article_id = normalize_ulid(value.article_id)
        author_id = UUID(str(value.author_id))
        revision_ids = tuple(
            dict.fromkeys(normalize_ulid(item) for item in value.revision_ids)
        )
        section_id = (
            UUID(str(value.section_id)) if value.section_id is not None else None
        )
        publication_state = str(value.publication_state)
        visibility = str(value.visibility)
    except (AttributeError, TypeError, ValueError):
        raise ExportRequestError(
            "exchange.export_snapshot_invalid.v1", "导出选择快照无效。"
        ) from None
    if (
        not revision_ids
        or publication_state not in {"DRAFT", "SCHEDULED", "PUBLISHED"}
        or visibility not in {"PUBLIC", "AUTHENTICATED", "PRIVATE"}
    ):
        raise ExportRequestError(
            "exchange.export_snapshot_invalid.v1", "导出选择快照无效。"
        )
    return _SelectionSnapshot(
        article_id=article_id,
        author_id=author_id,
        publication_state=publication_state,
        visibility=visibility,
        section_id=section_id,
        revision_ids=revision_ids,
        working_revision_id=_optional_ulid(value.working_revision_id),
        published_revision_id=_optional_ulid(value.published_revision_id),
        scheduled_revision_id=_optional_ulid(value.scheduled_revision_id),
        scheduled_for=value.scheduled_for,
        published_at=value.published_at,
        deleted_at=value.deleted_at,
        purge_after=value.purge_after,
    )


def _provider_error(exc: Exception) -> ExportRequestError | None:
    code = getattr(exc, "code", None)
    message = getattr(exc, "safe_message", None)
    if isinstance(code, str) and isinstance(message, str):
        return ExportRequestError(code, message)
    return None


def _running_error() -> ExportRequestError:
    return ExportRequestError(
        "exchange.export_running.v1", "已有导出任务正在进行，请等待其结束。"
    )


def request_export(
    *,
    actor_id,
    scope: str,
    scope_author_id,
    scope_section_id,
    article_ids,
    trace_code: str,
    client_ip: str,
    administrator_check: AdministratorCheck,
    selection_provider: SelectionProvider,
    audit_writer: AuditWriter,
    dispatcher: ExportDispatcher,
) -> ExportRequestResult:
    actor = _uuid(
        actor_id,
        code="exchange.export_admin_required.v1",
        message="只有管理员可以导出内容。",
    )
    if not all(
        callable(port)
        for port in (
            administrator_check,
            selection_provider,
            audit_writer,
            dispatcher,
        )
    ):
        raise TypeError("Export request ports are required")
    if not administrator_check(actor):
        raise ExportRequestError(
            "exchange.export_admin_required.v1", "只有管理员可以导出内容。"
        )
    selected_scope = _scope(scope)
    author, section, articles = _scope_inputs(
        scope=selected_scope,
        author_id=scope_author_id,
        section_id=scope_section_id,
        article_ids=article_ids,
    )
    if ExportJob.objects.filter(
        state__in=(ExportJob.State.RUNNING, ExportJob.State.CANCEL_REQUESTED)
    ).exists():
        raise _running_error()

    try:
        with transaction.atomic():
            job = ExportJob.objects.create(
                requested_by_id=actor,
                scope=selected_scope,
                scope_author_id=author,
                scope_section_id=section,
                requested_article_ids=list(articles),
                started_at=timezone.now(),
            )
            try:
                source = selection_provider(
                    scope=selected_scope,
                    scope_author_id=author,
                    scope_section_id=section,
                    article_ids=articles,
                )
                snapshots = tuple(_snapshot(item) for item in source)
            except Exception as exc:
                translated = _provider_error(exc)
                if translated is not None:
                    raise translated from None
                raise
            if not snapshots:
                raise ExportRequestError(
                    "exchange.export_empty.v1", "当前范围没有可导出的文章。"
                )
            if len({item.article_id for item in snapshots}) != len(snapshots):
                raise ExportRequestError(
                    "exchange.export_snapshot_invalid.v1", "导出选择快照无效。"
                )
            selections = [
                ExportSelection(
                    job=job,
                    ordinal=ordinal,
                    article_id=item.article_id,
                    author_id=item.author_id,
                    publication_state=item.publication_state,
                    visibility=item.visibility,
                    section_id=item.section_id,
                    revision_ids=list(item.revision_ids),
                    working_revision_id=item.working_revision_id,
                    published_revision_id=item.published_revision_id,
                    scheduled_revision_id=item.scheduled_revision_id,
                    scheduled_for=item.scheduled_for,
                    published_at=item.published_at,
                    deleted_at=item.deleted_at,
                    purge_after=item.purge_after,
                )
                for ordinal, item in enumerate(snapshots, start=1)
            ]
            ExportSelection.objects.bulk_create(selections)
            other_author_count = sum(item.author_id != actor for item in snapshots)
            job.selection_summary = {
                "other_author_count": other_author_count,
                "selected_count": len(snapshots),
            }
            job.save(update_fields=("selection_summary",))
            audit_writer(
                action="exchange.export.requested",
                actor_id=actor,
                target_id=job.id,
                trace_code=trace_code,
                client_ip=client_ip,
                before={},
                after={
                    "other_author_count": other_author_count,
                    "scope": selected_scope,
                    "selected_count": len(snapshots),
                },
                summary="Administrator requested content export",
            )
            transaction.on_commit(lambda: dispatcher(job.id))
    except IntegrityError:
        if ExportJob.objects.filter(
            state__in=(ExportJob.State.RUNNING, ExportJob.State.CANCEL_REQUESTED)
        ).exists():
            raise _running_error() from None
        raise
    return ExportRequestResult(job.id, job.state, len(snapshots))
