from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

from django.db import transaction

from apps.core.ids import normalize_ulid
from apps.exchange.models import ImportItem, ImportJob

AuthorCheck = Callable[[UUID], bool]
AuditWriter = Callable[..., object]


class ImportDecisionError(ValueError):
    def __init__(self, code: str, message: str = "导入预览无法更新。") -> None:
        self.code = code
        self.safe_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ImportConflictFacts:
    id_owner_id: UUID | None
    exact_title_owner_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ImportMetadataMapping:
    section_id: UUID | None
    tag_ids: tuple[UUID, ...]
    proposed_tag_names: tuple[str, ...]


class ConflictFactsProvider(Protocol):
    def __call__(
        self, *, imported_article_id: str | None, title: str
    ) -> ImportConflictFacts: ...


class MetadataResolver(Protocol):
    def __call__(
        self, *, section_name: object, tag_names: object
    ) -> ImportMetadataMapping: ...


class MappingValidator(Protocol):
    def __call__(
        self,
        *,
        section_id: UUID | str | None,
        tag_ids: object,
        proposed_tag_names: object,
    ) -> ImportMetadataMapping: ...


@dataclass(frozen=True, slots=True)
class ImportPreviewItem:
    item_id: str
    item_path: str
    title: str
    parse_status: str
    classification: str | None
    decision: str | None
    included: bool
    target_article_id: str | None
    mapped_section_id: UUID | None
    mapped_tag_ids: tuple[UUID, ...]
    proposed_tag_names: tuple[str, ...]
    conflict_summary: Mapping[str, object]
    preview_html: str
    parse_error_code: str
    result_status: str
    result_reason_code: str
    result_article_id: str | None
    result_revision_id: str | None


@dataclass(frozen=True, slots=True)
class ImportPreview:
    job_id: str
    status: str
    preview_version: int
    preview_summary: Mapping[str, object]
    confirmed_preview_version: int | None
    result_summary: Mapping[str, object]
    items: tuple[ImportPreviewItem, ...]


@dataclass(frozen=True, slots=True)
class ImportDecisionResult:
    job_id: str
    item_id: str
    preview_version: int


def _actor_id(value: UUID | str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ImportDecisionError(
            "exchange.import_not_found.v1", "未找到导入预览。"
        ) from None


def _job_id(value: str) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ImportDecisionError(
            "exchange.import_not_found.v1", "未找到导入预览。"
        ) from None


def _item_id(value: str) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ImportDecisionError(
            "exchange.import_item_not_found.v1", "未找到导入条目。"
        ) from None


def _preview_version(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ImportDecisionError(
            "exchange.import_preview_conflict.v1", "导入预览已变化，请刷新后重试。"
        )
    return value


def _preview_item(item: ImportItem) -> ImportPreviewItem:
    return ImportPreviewItem(
        item_id=item.id,
        item_path=item.item_path,
        title=item.detected_title,
        parse_status=item.parse_status,
        classification=item.classification,
        decision=item.decision,
        included=item.included,
        target_article_id=item.target_article_id,
        mapped_section_id=item.mapped_section_id,
        mapped_tag_ids=tuple(UUID(value) for value in item.mapped_tag_ids),
        proposed_tag_names=tuple(item.proposed_tag_names),
        conflict_summary=MappingProxyType(dict(item.conflict_summary)),
        preview_html=item.preview_html,
        parse_error_code=item.parse_error_code,
        result_status=item.result_status,
        result_reason_code=item.result_reason_code,
        result_article_id=item.result_article_id,
        result_revision_id=item.result_revision_id,
    )


def _preview(job: ImportJob) -> ImportPreview:
    return ImportPreview(
        job_id=job.id,
        status=job.status,
        preview_version=job.preview_version,
        preview_summary=MappingProxyType(dict(job.preview_summary)),
        confirmed_preview_version=job.confirmed_preview_version,
        result_summary=MappingProxyType(dict(job.result_summary)),
        items=tuple(_preview_item(item) for item in job.items.order_by("ordinal")),
    )


def import_preview(*, actor_id: UUID | str, job_id: str) -> ImportPreview:
    actor = _actor_id(actor_id)
    job = ImportJob.objects.filter(pk=_job_id(job_id), author_id=actor).first()
    if job is None:
        raise ImportDecisionError("exchange.import_not_found.v1", "未找到导入预览。")
    return _preview(job)


def _owner_scope(actor_id: UUID, owner_ids: tuple[UUID, ...]) -> str:
    own = actor_id in owner_ids
    foreign = any(owner_id != actor_id for owner_id in owner_ids)
    if own and foreign:
        return "MIXED"
    return "SELF" if own else "FOREIGN"


def _classify(
    *, actor_id: UUID, item: ImportItem, facts: ImportConflictFacts
) -> tuple[str, str, bool, str | None, dict[str, object]]:
    if not isinstance(facts, ImportConflictFacts):
        raise TypeError("Conflict facts provider returned an invalid result")
    if facts.id_owner_id is not None:
        scope = "SELF" if facts.id_owner_id == actor_id else "FOREIGN"
        if scope == "SELF":
            return (
                ImportItem.Classification.DUPLICATE_ID,
                ImportItem.Decision.SKIP,
                True,
                item.imported_article_id,
                {"match_count": 1, "owner_scope": scope},
            )
        return (
            ImportItem.Classification.FOREIGN_CONFLICT,
            ImportItem.Decision.SKIP,
            False,
            None,
            {"match_count": 1, "owner_scope": scope},
        )
    if item.imported_article_id is None and facts.exact_title_owner_ids:
        return (
            ImportItem.Classification.TITLE_WARNING,
            ImportItem.Decision.SKIP,
            True,
            None,
            {
                "match_count": len(facts.exact_title_owner_ids),
                "owner_scope": _owner_scope(actor_id, facts.exact_title_owner_ids),
            },
        )
    return ImportItem.Classification.NEW, ImportItem.Decision.CREATE, True, None, {}


def _mark_invalid(item: ImportItem, code: str) -> None:
    item.parse_status = ImportItem.ParseStatus.INVALID
    item.classification = ImportItem.Classification.INVALID
    item.decision = ImportItem.Decision.SKIP
    item.included = False
    item.target_article_id = None
    item.mapped_section_id = None
    item.mapped_tag_ids = []
    item.proposed_tag_names = []
    item.conflict_summary = {}
    item.parse_error_code = code


def classify_import_preview(
    *,
    actor_id: UUID | str,
    job_id: str,
    conflict_facts: ConflictFactsProvider,
    metadata_resolver: MetadataResolver,
) -> ImportPreview:
    actor = _actor_id(actor_id)
    if not callable(conflict_facts) or not callable(metadata_resolver):
        raise TypeError("Import classification ports are required")
    with transaction.atomic():
        job = (
            ImportJob.objects.select_for_update()
            .filter(
                pk=_job_id(job_id),
                author_id=actor,
                status=ImportJob.Status.PREVIEW_READY,
            )
            .first()
        )
        if job is None:
            raise ImportDecisionError(
                "exchange.import_not_found.v1", "未找到导入预览。"
            )
        valid = 0
        invalid = 0
        for item in job.items.select_for_update().order_by("ordinal"):
            if item.parse_status == ImportItem.ParseStatus.INVALID:
                _mark_invalid(item, item.parse_error_code)
                invalid += 1
            else:
                try:
                    facts = conflict_facts(
                        imported_article_id=item.imported_article_id,
                        title=item.detected_title,
                    )
                    mapping = metadata_resolver(
                        section_name=item.front_matter.get("section"),
                        tag_names=item.front_matter.get("tags", ()),
                    )
                    if not isinstance(mapping, ImportMetadataMapping):
                        raise TypeError("Metadata resolver returned an invalid result")
                except ImportDecisionError as exc:
                    _mark_invalid(item, exc.code)
                    invalid += 1
                else:
                    (
                        item.classification,
                        item.decision,
                        item.included,
                        item.target_article_id,
                        item.conflict_summary,
                    ) = _classify(actor_id=actor, item=item, facts=facts)
                    item.mapped_section_id = mapping.section_id
                    item.mapped_tag_ids = [str(value) for value in mapping.tag_ids]
                    item.proposed_tag_names = list(mapping.proposed_tag_names)
                    valid += 1
            item.save(
                update_fields=(
                    "parse_status",
                    "classification",
                    "decision",
                    "included",
                    "target_article_id",
                    "mapped_section_id",
                    "mapped_tag_ids",
                    "proposed_tag_names",
                    "conflict_summary",
                    "parse_error_code",
                )
            )
        job.preview_summary = {
            "invalid": invalid,
            "total": valid + invalid,
            "valid": valid,
        }
        job.save(update_fields=("preview_summary",))
        return _preview(job)


def _decision(value: str) -> str:
    try:
        return ImportItem.Decision(value)
    except (TypeError, ValueError):
        raise ImportDecisionError(
            "exchange.import_decision_invalid.v1", "导入条目的处理方式无效。"
        ) from None


def _decision_is_allowed(
    *, classification: str | None, included: bool, decision: str
) -> bool:
    if classification is None or type(included) is not bool:
        return False
    if not included:
        return decision == ImportItem.Decision.SKIP
    allowed = {
        ImportItem.Classification.NEW: {ImportItem.Decision.CREATE},
        ImportItem.Classification.TITLE_WARNING: {
            ImportItem.Decision.SKIP,
            ImportItem.Decision.CREATE,
        },
        ImportItem.Classification.DUPLICATE_ID: {
            ImportItem.Decision.SKIP,
            ImportItem.Decision.UPDATE,
            ImportItem.Decision.CREATE,
        },
        ImportItem.Classification.FOREIGN_CONFLICT: set(),
        ImportItem.Classification.INVALID: set(),
    }
    return decision in allowed.get(classification, set())


def update_import_decision(
    *,
    actor_id: UUID | str,
    job_id: str,
    item_id: str,
    expected_preview_version: int,
    included: bool,
    decision: str,
    section_id: UUID | str | None,
    tag_ids: object,
    proposed_tag_names: object,
    trace_code: str,
    client_ip: str,
    author_check: AuthorCheck,
    mapping_validator: MappingValidator,
    audit_writer: AuditWriter,
) -> ImportDecisionResult:
    actor = _actor_id(actor_id)
    expected_version = _preview_version(expected_preview_version)
    selected_decision = _decision(decision)
    if not all(
        callable(port) for port in (author_check, mapping_validator, audit_writer)
    ):
        raise TypeError("Import decision ports are required")
    if not author_check(actor):
        raise ImportDecisionError(
            "exchange.import_author_required.v1",
            "只有启用的作者可以修改导入预览。",
        )
    with transaction.atomic():
        job = (
            ImportJob.objects.select_for_update()
            .filter(pk=_job_id(job_id), author_id=actor)
            .first()
        )
        if job is None:
            raise ImportDecisionError(
                "exchange.import_not_found.v1", "未找到导入预览。"
            )
        if job.status != ImportJob.Status.PREVIEW_READY:
            raise ImportDecisionError(
                "exchange.import_preview_not_ready.v1", "导入预览当前不可修改。"
            )
        if job.preview_version != expected_version:
            raise ImportDecisionError(
                "exchange.import_preview_conflict.v1",
                "导入预览已变化，请刷新后重试。",
            )
        item = (
            ImportItem.objects.select_for_update()
            .filter(pk=_item_id(item_id), job=job)
            .first()
        )
        if item is None:
            raise ImportDecisionError(
                "exchange.import_item_not_found.v1", "未找到导入条目。"
            )
        if not _decision_is_allowed(
            classification=item.classification,
            included=included,
            decision=selected_decision,
        ):
            raise ImportDecisionError(
                "exchange.import_decision_invalid.v1",
                "该导入条目不能使用所选处理方式。",
            )
        mapping = mapping_validator(
            section_id=section_id,
            tag_ids=tag_ids,
            proposed_tag_names=proposed_tag_names,
        )
        if not isinstance(mapping, ImportMetadataMapping):
            raise TypeError("Mapping validator returned an invalid result")
        before_version = job.preview_version
        item.included = included
        item.decision = selected_decision
        item.mapped_section_id = mapping.section_id
        item.mapped_tag_ids = [str(value) for value in mapping.tag_ids]
        item.proposed_tag_names = list(mapping.proposed_tag_names)
        item.save(
            update_fields=(
                "included",
                "decision",
                "mapped_section_id",
                "mapped_tag_ids",
                "proposed_tag_names",
            )
        )
        job.preview_version += 1
        job.save(update_fields=("preview_version",))
        audit_writer(
            action="exchange.import_decision.updated",
            actor_id=actor,
            target_id=job.id,
            trace_code=trace_code,
            client_ip=client_ip,
            before={"preview_version": before_version},
            after={
                "preview_version": job.preview_version,
                "item_id": item.id,
                "included": included,
                "decision": selected_decision,
                "section_mapped": mapping.section_id is not None,
                "tag_count": len(mapping.tag_ids),
                "proposed_tag_count": len(mapping.proposed_tag_names),
            },
            summary="Import preview decision updated",
        )
        return ImportDecisionResult(job.id, item.id, job.preview_version)
