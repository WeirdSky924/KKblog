from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.public import is_active_author, is_administrator
from apps.core.events import enqueue_event
from apps.operations.public import record_audit_entry

from ..events import TAG_CHANGED, TAG_RESTORE_CONFLICT, TAG_REVIEWED
from ..models import (
    Article,
    ArticleTag,
    Tag,
    TagAssociationHistory,
    TagRestoreConflict,
)
from ..models.tag import normalize_tag_name


class TagCommandError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.safe_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class TagResult:
    tag_id: UUID
    name: str
    state: str


@dataclass(frozen=True, slots=True)
class TagDeleteResult:
    tag_id: UUID
    affected_article_count: int


@dataclass(frozen=True, slots=True)
class TagRestoreResult:
    tag_id: UUID
    restored_article_count: int
    conflict_count: int


def _identity(value, code: str, message: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise TagCommandError(code, message) from None


def _author(value) -> UUID:
    actor = _identity(
        value,
        "content.tag_author_required.v1",
        "只有启用的作者可以提议标签。",
    )
    if not is_active_author(actor):
        raise TagCommandError(
            "content.tag_author_required.v1", "只有启用的作者可以提议标签。"
        )
    return actor


def _admin(value) -> UUID:
    actor = _identity(
        value,
        "content.tag_admin_required.v1",
        "只有管理员可以管理标签。",
    )
    if not is_administrator(actor):
        raise TagCommandError(
            "content.tag_admin_required.v1", "只有管理员可以管理标签。"
        )
    return actor


def _tag_id(value) -> UUID:
    return _identity(value, "content.tag_not_found.v1", "标签不存在。")


def _name(value: str) -> tuple[str, str]:
    try:
        return normalize_tag_name(value)
    except ValidationError:
        raise TagCommandError(
            "content.tag_name_invalid.v1", "标签名称须为 1 至 50 个字符。"
        ) from None


def _changed(*, tag_id: UUID, actor_id: UUID, trace_code: str, action: str) -> None:
    enqueue_event(
        TAG_CHANGED,
        aggregate_type="tag",
        aggregate_id=str(tag_id),
        actor_id=actor_id,
        trace_code=trace_code,
        payload={"action": action},
    )


def propose_tag(*, actor_id, name: str) -> TagResult:
    actor = _author(actor_id)
    tag = _propose_tag(actor_id=actor, name=name)
    return TagResult(tag.id, tag.name, tag.state)


def _existing_tag_for_update(normalized_name: str) -> Tag | None:
    tags = tuple(
        Tag.objects.select_for_update()
        .filter(normalized_name=normalized_name)
        .order_by("created_at", "id")
    )
    for state in (
        Tag.State.ACTIVE,
        Tag.State.PENDING,
        Tag.State.REJECTED,
        Tag.State.DELETED,
    ):
        for tag in tags:
            if tag.state == state:
                return tag
    return None


def _reuse_tag_proposal(*, tag: Tag, actor_id: UUID, display_name: str) -> Tag:
    if tag.state in {Tag.State.PENDING, Tag.State.ACTIVE}:
        return tag
    if tag.state == Tag.State.DELETED:
        raise TagCommandError(
            "content.tag_name_conflict.v1", "标签已被删除，请联系管理员恢复。"
        )
    if tag.state != Tag.State.REJECTED:
        raise TagCommandError(
            "content.tag_name_conflict.v1", "标签名称已存在且不可使用。"
        )
    tag.name = display_name
    tag.state = Tag.State.PENDING
    tag.proposed_by_id = actor_id
    tag.reviewed_by_id = None
    tag.reviewed_at = None
    tag.save(
        update_fields=(
            "name",
            "state",
            "proposed_by",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        )
    )
    return tag


def _propose_tag(*, actor_id: UUID, name: str) -> Tag:
    display, normalized = _name(name)
    try:
        with transaction.atomic():
            tag = _existing_tag_for_update(normalized)
            if tag is not None:
                return _reuse_tag_proposal(
                    tag=tag,
                    actor_id=actor_id,
                    display_name=display,
                )
            return Tag.objects.create(
                name=display,
                normalized_name=normalized,
                state=Tag.State.PENDING,
                proposed_by_id=actor_id,
            )
    except IntegrityError:
        with transaction.atomic():
            tag = _existing_tag_for_update(normalized)
            if tag is None:
                raise TagCommandError(
                    "content.tag_name_conflict.v1", "标签名称已存在且不可使用。"
                ) from None
            return _reuse_tag_proposal(
                tag=tag,
                actor_id=actor_id,
                display_name=display,
            )


def resolve_proposed_tags(*, actor_id, names: tuple[str, ...]) -> tuple[UUID, ...]:
    actor = _author(actor_id)
    if not isinstance(names, tuple):
        raise TagCommandError("content.tag_name_invalid.v1", "标签申请信息不合法。")
    resolved: list[UUID] = []
    for name in names:
        tag = _propose_tag(actor_id=actor, name=name)
        if tag.id not in resolved:
            resolved.append(tag.id)
    return tuple(resolved)


def create_tag(*, actor_id, name: str, trace_code: str, client_ip: str) -> TagResult:
    actor = _admin(actor_id)
    display, normalized = _name(name)
    try:
        with transaction.atomic():
            tag = Tag.objects.create(
                name=display,
                normalized_name=normalized,
                state=Tag.State.ACTIVE,
                reviewed_by_id=actor,
                reviewed_at=timezone.now(),
            )
            record_audit_entry(
                action="content.tag.create",
                actor_id=actor,
                target_id=str(tag.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before={},
                after={
                    "name": tag.name,
                    "normalized_name": tag.normalized_name,
                    "state": tag.state,
                },
                summary="Create active article tag",
            )
            _changed(
                tag_id=tag.id,
                actor_id=actor,
                trace_code=trace_code,
                action="created",
            )
    except IntegrityError:
        raise TagCommandError(
            "content.tag_name_conflict.v1", "标签名称已存在。"
        ) from None
    return TagResult(tag.id, tag.name, tag.state)


def _lock_articles_for_tag(tag_id: UUID) -> tuple[Article, ...]:
    article_ids = list(
        ArticleTag.objects.filter(tag_id=tag_id)
        .order_by("article_id")
        .values_list("article_id", flat=True)
    )
    return tuple(
        Article.objects.select_for_update().filter(pk__in=article_ids).order_by("id")
    )


def review_tag(
    *,
    actor_id,
    tag_id,
    approved: bool,
    trace_code: str,
    client_ip: str,
) -> TagResult:
    actor = _admin(actor_id)
    identity = _tag_id(tag_id)
    if type(approved) is not bool:
        raise TagCommandError("content.tag_review_invalid.v1", "审核结果不合法。")
    with transaction.atomic():
        affected_articles = _lock_articles_for_tag(identity)
        try:
            tag = Tag.objects.select_for_update().get(pk=identity)
        except Tag.DoesNotExist:
            raise TagCommandError("content.tag_not_found.v1", "标签不存在。") from None
        if tag.state != Tag.State.PENDING:
            raise TagCommandError("content.tag_review_invalid.v1", "标签当前不能审核。")
        if not Article.objects.filter(
            publication_state=Article.PublicationState.PUBLISHED,
            deleted_at__isnull=True,
            published_revision__tag_snapshots__tag_id=identity,
        ).exists():
            raise TagCommandError(
                "content.tag_not_published.v1",
                "标签尚未随文章发布，当前不能审核。",
            )
        previous = tag.state
        tag.state = Tag.State.ACTIVE if approved else Tag.State.REJECTED
        tag.reviewed_by_id = actor
        tag.reviewed_at = timezone.now()
        tag.save(update_fields=("state", "reviewed_by", "reviewed_at", "updated_at"))
        if not approved:
            ArticleTag.objects.filter(tag=tag).delete()
        outcome = "approved" if approved else "rejected"
        record_audit_entry(
            action="content.tag.review",
            actor_id=actor,
            target_id=str(tag.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before={"state": previous},
            after={"state": tag.state, "outcome": outcome},
            summary="Review proposed article tag",
        )
        _changed(
            tag_id=tag.id,
            actor_id=actor,
            trace_code=trace_code,
            action=outcome,
        )
        recipients = {article.author_id for article in affected_articles}
        if tag.proposed_by_id is not None:
            recipients.add(tag.proposed_by_id)
        for recipient_id in sorted(recipients, key=str):
            enqueue_event(
                TAG_REVIEWED,
                aggregate_type="tag",
                aggregate_id=str(tag.id),
                actor_id=actor,
                trace_code=trace_code,
                payload={
                    "outcome": outcome,
                    "recipient_id": str(recipient_id),
                },
            )
    return TagResult(tag.id, tag.name, tag.state)


def delete_tag(*, actor_id, tag_id, trace_code: str, client_ip: str) -> TagDeleteResult:
    actor = _admin(actor_id)
    identity = _tag_id(tag_id)
    with transaction.atomic():
        _lock_articles_for_tag(identity)
        try:
            tag = Tag.objects.select_for_update().get(pk=identity)
        except Tag.DoesNotExist:
            raise TagCommandError("content.tag_not_found.v1", "标签不存在。") from None
        if tag.state != Tag.State.ACTIVE:
            raise TagCommandError(
                "content.tag_delete_invalid.v1", "只有全站标签可以删除。"
            )
        associations = tuple(ArticleTag.objects.filter(tag=tag).order_by("article_id"))
        now = timezone.now()
        for association in associations:
            TagAssociationHistory.objects.update_or_create(
                tag=tag,
                article_id=association.article_id,
                defaults={"removed_at": now, "restored_at": None},
            )
        ArticleTag.objects.filter(tag=tag).delete()
        previous = tag.state
        tag.state = Tag.State.DELETED
        tag.reviewed_by_id = actor
        tag.reviewed_at = now
        tag.save(update_fields=("state", "reviewed_by", "reviewed_at", "updated_at"))
        record_audit_entry(
            action="content.tag.delete",
            actor_id=actor,
            target_id=str(tag.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before={"state": previous},
            after={"state": tag.state, "affected_count": len(associations)},
            summary="Delete global article tag",
        )
        _changed(
            tag_id=tag.id,
            actor_id=actor,
            trace_code=trace_code,
            action="deleted",
        )
    return TagDeleteResult(tag.id, len(associations))


def restore_tag(
    *, actor_id, tag_id, trace_code: str, client_ip: str
) -> TagRestoreResult:
    actor = _admin(actor_id)
    identity = _tag_id(tag_id)
    history_ids = list(
        TagAssociationHistory.objects.filter(tag_id=identity, restored_at__isnull=True)
        .order_by("article_id")
        .values_list("article_id", flat=True)
    )
    restored_count = 0
    conflict_count = 0
    with transaction.atomic():
        articles = {
            article.id: article
            for article in Article.objects.select_for_update()
            .filter(pk__in=history_ids)
            .order_by("id")
        }
        try:
            tag = Tag.objects.select_for_update().get(pk=identity)
        except Tag.DoesNotExist:
            raise TagCommandError("content.tag_not_found.v1", "标签不存在。") from None
        if tag.state not in {Tag.State.DELETED, Tag.State.ACTIVE}:
            raise TagCommandError(
                "content.tag_restore_invalid.v1", "标签当前不能恢复。"
            )
        previous = tag.state
        if tag.state == Tag.State.DELETED:
            tag.state = Tag.State.ACTIVE
            tag.reviewed_by_id = actor
            tag.reviewed_at = timezone.now()
            try:
                tag.save(
                    update_fields=(
                        "state",
                        "reviewed_by",
                        "reviewed_at",
                        "updated_at",
                    )
                )
            except IntegrityError:
                raise TagCommandError(
                    "content.tag_name_conflict.v1", "同名标签已存在，无法恢复。"
                ) from None

        now = timezone.now()
        histories = tuple(
            TagAssociationHistory.objects.select_for_update()
            .filter(tag=tag, restored_at__isnull=True)
            .order_by("article_id")
        )
        for history in histories:
            article = articles.get(history.article_id)
            if article is None:
                history.restored_at = now
                history.save(update_fields=("restored_at",))
                continue
            if ArticleTag.objects.filter(article=article, tag=tag).exists():
                history.restored_at = now
                history.save(update_fields=("restored_at",))
                TagRestoreConflict.objects.filter(
                    tag=tag,
                    article_id=article.id,
                    resolved_at__isnull=True,
                ).update(resolved_at=now)
                continue
            if ArticleTag.objects.filter(article=article).count() >= 10:
                conflict, created = TagRestoreConflict.objects.get_or_create(
                    tag=tag,
                    article_id=article.id,
                    resolved_at=None,
                )
                del conflict
                conflict_count += 1
                if created:
                    enqueue_event(
                        TAG_RESTORE_CONFLICT,
                        aggregate_type="tag",
                        aggregate_id=str(tag.id),
                        actor_id=actor,
                        trace_code=trace_code,
                        payload={
                            "article_id": article.id,
                            "recipient_id": str(actor),
                        },
                    )
                continue
            ArticleTag.objects.create(article=article, tag=tag)
            history.restored_at = now
            history.save(update_fields=("restored_at",))
            TagRestoreConflict.objects.filter(
                tag=tag,
                article_id=article.id,
                resolved_at__isnull=True,
            ).update(resolved_at=now)
            restored_count += 1

        record_audit_entry(
            action="content.tag.restore",
            actor_id=actor,
            target_id=str(tag.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before={"state": previous},
            after={
                "state": tag.state,
                "restored_count": restored_count,
                "conflict_count": conflict_count,
            },
            summary="Restore global article tag",
        )
        _changed(
            tag_id=tag.id,
            actor_id=actor,
            trace_code=trace_code,
            action="restored",
        )
    return TagRestoreResult(tag.id, restored_count, conflict_count)
