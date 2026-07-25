from dataclasses import dataclass
from enum import StrEnum
from ipaddress import IPv6Address, ip_address
from uuid import UUID

from django.db import IntegrityError, transaction

from apps.content.public import (
    ArticleDeletionError,
    ArticleModerationBoundaryError,
    delete_article,
    prepare_article_moderation_action,
    restore_article_from_moderation,
)
from apps.core.events import enqueue_event
from apps.core.ids import new_ulid, normalize_ulid
from apps.core.time.clock import Clock, SystemClock, require_aware
from apps.operations.public import record_audit_entry

from ..events import ARTICLE_MODERATED, ARTICLE_MODERATION_RESTORED
from ..models import ArticleModerationCase
from ..ports import ModerationAccountPolicy, default_moderation_account_policy


class ArticleAction(StrEnum):
    HIDE = "HIDE"
    DELETE = "DELETE"


class ArticleCaseError(ValueError):
    def __init__(self, code: str, safe_message: str, *, field: str | None = None):
        self.code = code
        self.safe_message = safe_message
        self.field = field
        super().__init__(safe_message)


@dataclass(frozen=True, slots=True)
class ArticleCaseResult:
    case_id: str
    article_id: str
    action: str
    state: str
    article_changed: bool
    recipient_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ArticleCaseRestorationResult:
    case_id: str
    article_id: str
    state: str
    article_changed: bool
    recovery_status: str
    recipient_ids: tuple[UUID, ...]


def _actor(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ArticleCaseError(
            "moderation.article_action_not_allowed.v1",
            "当前身份不能管理该文章。",
        ) from None


def _client_ip(value: str) -> str:
    try:
        parsed = ip_address(value)
    except (TypeError, ValueError):
        raise ArticleCaseError(
            "moderation.network_invalid.v1",
            "当前网络信息无效。",
        ) from None
    if isinstance(parsed, IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    return str(parsed)


def _administrator(
    *,
    actor_id,
    client_ip: str,
    account_policy: ModerationAccountPolicy,
) -> tuple[UUID, str]:
    actor = _actor(actor_id)
    address = _client_ip(client_ip)
    if (
        not account_policy.is_active_account(actor)
        or account_policy.is_ip_blocked(address)
        or not account_policy.is_administrator(actor)
    ):
        raise ArticleCaseError(
            "moderation.article_action_not_allowed.v1",
            "当前身份不能管理该文章。",
        )
    return actor, address


def _action(value) -> ArticleAction:
    try:
        return ArticleAction(value)
    except (TypeError, ValueError):
        raise ArticleCaseError(
            "moderation.article_action_invalid.v1",
            "请选择有效的文章管理动作。",
            field="action",
        ) from None


def _text(value, *, field: str) -> str:
    if not isinstance(value, str):
        raise ArticleCaseError(
            "moderation.article_reason_invalid.v1",
            "说明需为 200 个字符以内的纯文本。",
            field=field,
        )
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if (
        len(normalized) > 200
        or "<" in normalized
        or ">" in normalized
        or "://" in normalized
        or any(
            not character.isprintable() and character not in "\n\t"
            for character in normalized
        )
    ):
        raise ArticleCaseError(
            "moderation.article_reason_invalid.v1",
            "说明需为 200 个字符以内的纯文本。",
            field=field,
        )
    return normalized


def _case_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ArticleCaseError(
            "moderation.article_case_unavailable.v1",
            "当前文章案件不可用。",
        ) from None


def _boundary_error(exc: ArticleModerationBoundaryError) -> ArticleCaseError:
    code = (
        "moderation.article_hide_not_allowed.v1"
        if exc.code == "content.article_hide_not_allowed.v1"
        else "moderation.article_action_not_allowed.v1"
    )
    return ArticleCaseError(code, exc.safe_message)


def create_article_moderation_case(
    *,
    actor_id,
    article_id: str,
    action,
    reason: str,
    client_ip: str,
    trace_code: str,
    account_policy: ModerationAccountPolicy | None = None,
    clock: Clock | None = None,
) -> ArticleCaseResult:
    accounts = account_policy or default_moderation_account_policy()
    actor, address = _administrator(
        actor_id=actor_id,
        client_ip=client_ip,
        account_policy=accounts,
    )
    normalized_action = _action(action)
    normalized_reason = _text(reason, field="reason")
    active_clock = clock or SystemClock()
    acted_at = require_aware(active_clock.now())
    case_id = new_ulid()
    try:
        with transaction.atomic():
            if (
                ArticleModerationCase.objects.select_for_update()
                .filter(
                    article_id=article_id,
                    state__in=("ACTIVE", "APPEALED", "FINAL_UPHELD"),
                )
                .exists()
            ):
                raise ArticleCaseError(
                    "moderation.article_case_state_conflict.v1",
                    "该文章已有生效中的管理案件。",
                )
            try:
                target = prepare_article_moderation_action(
                    actor_id=actor,
                    article_id=article_id,
                    action=normalized_action,
                )
            except ArticleModerationBoundaryError as exc:
                raise _boundary_error(exc) from None
            case = ArticleModerationCase.objects.create(
                id=case_id,
                article_id=target.article_id,
                author_id=target.author_id,
                action=normalized_action,
                pre_action_snapshot=target.safe_snapshot(),
                reason=normalized_reason,
                acted_by_id=actor,
                acted_at=acted_at,
            )
            article_changed = False
            if normalized_action == ArticleAction.DELETE:
                try:
                    deletion = delete_article(
                        actor_id=actor,
                        article_id=target.article_id,
                        expected_row_version=target.row_version,
                        administrative=True,
                        trace_code=trace_code,
                        client_ip=address,
                        moderation_case_id=case.id,
                        clock=active_clock,
                    )
                except ArticleDeletionError as exc:
                    raise ArticleCaseError(
                        "moderation.article_action_not_allowed.v1",
                        exc.safe_message,
                    ) from None
                article_changed = deletion.changed
            record_audit_entry(
                action="moderation.article.action",
                actor_id=actor,
                target_id=case.article_id,
                trace_code=trace_code,
                client_ip=address,
                before={
                    "publication_state": target.publication_state,
                    "visibility": target.visibility,
                },
                after={
                    "action": case.action,
                    "article_changed": article_changed,
                    "case_id": case.id,
                    "reason_provided": bool(normalized_reason),
                    "snapshot_version": 1,
                    "state": case.state,
                },
                summary="Administrator moderated article",
            )
            enqueue_event(
                ARTICLE_MODERATED,
                aggregate_type="article",
                aggregate_id=case.article_id,
                actor_id=actor,
                trace_code=trace_code,
                payload={
                    "case_id": case.id,
                    "action": case.action,
                    "reason": normalized_reason,
                    "recipient_id": str(case.author_id),
                },
                clock=active_clock,
            )
    except IntegrityError:
        raise ArticleCaseError(
            "moderation.article_case_state_conflict.v1",
            "该文章已有生效中的管理案件。",
        ) from None
    return ArticleCaseResult(
        case.id,
        case.article_id,
        case.action,
        case.state,
        article_changed,
        (case.author_id,),
    )


def restore_article_moderation_case(
    *,
    actor_id,
    case_id: str,
    client_ip: str,
    trace_code: str,
    account_policy: ModerationAccountPolicy | None = None,
    clock: Clock | None = None,
) -> ArticleCaseRestorationResult:
    accounts = account_policy or default_moderation_account_policy()
    actor, address = _administrator(
        actor_id=actor_id,
        client_ip=client_ip,
        account_policy=accounts,
    )
    identity = _case_id(case_id)
    active_clock = clock or SystemClock()
    resolved_at = require_aware(active_clock.now())
    with transaction.atomic():
        case = (
            ArticleModerationCase.objects.select_for_update()
            .filter(pk=identity)
            .first()
        )
        if case is None or case.state != ArticleModerationCase.State.ACTIVE:
            raise ArticleCaseError(
                "moderation.article_case_state_conflict.v1",
                "该文章案件已经恢复或当前不可用。",
            )
        try:
            recovery = restore_article_from_moderation(
                actor_id=actor,
                case_id=case.id,
                article_id=case.article_id,
                action=case.action,
                pre_action_snapshot=case.pre_action_snapshot,
                trace_code=trace_code,
                client_ip=address,
                clock=active_clock,
            )
        except ArticleModerationBoundaryError as exc:
            raise ArticleCaseError(
                "moderation.article_recovery_failed.v1",
                exc.safe_message,
            ) from None
        case.state = ArticleModerationCase.State.RESTORED
        case.resolved_by_id = actor
        case.resolved_at = resolved_at
        case.save(
            update_fields=(
                "state",
                "resolved_by_id",
                "resolved_at",
                "updated_at",
            )
        )
        record_audit_entry(
            action="moderation.article.restore",
            actor_id=actor,
            target_id=case.article_id,
            trace_code=trace_code,
            client_ip=address,
            before={"action": case.action, "state": ArticleModerationCase.State.ACTIVE},
            after={
                "article_changed": recovery.changed,
                "case_id": case.id,
                "recovery_status": "RESTORED",
                "state": case.state,
            },
            summary="Administrator restored moderated article",
        )
        enqueue_event(
            ARTICLE_MODERATION_RESTORED,
            aggregate_type="article",
            aggregate_id=case.article_id,
            actor_id=actor,
            trace_code=trace_code,
            payload={
                "case_id": case.id,
                "action": case.action,
                "recipient_id": str(case.author_id),
                "recovery_status": "RESTORED",
            },
            clock=active_clock,
        )
    return ArticleCaseRestorationResult(
        case.id,
        case.article_id,
        case.state,
        recovery.changed,
        "RESTORED",
        (case.author_id,),
    )
