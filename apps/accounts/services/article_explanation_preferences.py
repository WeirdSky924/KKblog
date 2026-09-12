from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from apps.accounts.models import Account


class ArticleExplanationPreferenceError(ValueError):
    def __init__(self, message: str = "文章解释偏好不可用。") -> None:
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ArticleExplanationPreferences:
    auto_accept: bool


def _identity(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ArticleExplanationPreferenceError from None


def _active_account(account_id: UUID, *, for_update: bool = False) -> Account:
    accounts = Account.objects.select_for_update() if for_update else Account.objects
    try:
        return accounts.get(pk=account_id, status=Account.Status.ACTIVE)
    except Account.DoesNotExist:
        raise ArticleExplanationPreferenceError from None


def article_explanation_preferences(*, account_id) -> ArticleExplanationPreferences:
    account = _active_account(_identity(account_id))
    return ArticleExplanationPreferences(account.article_explanation_auto_accept)


def change_article_explanation_preferences(
    *,
    account_id,
    auto_accept: bool,
    client_ip: str,
    trace_code: str,
    audit_writer,
) -> ArticleExplanationPreferences:
    if type(auto_accept) is not bool:
        raise ArticleExplanationPreferenceError("请选择有效的文章解释偏好。")
    if not callable(audit_writer):
        raise TypeError("audit_writer must be callable")
    identity = _identity(account_id)
    with transaction.atomic():
        account = _active_account(identity, for_update=True)
        before = {
            "article_explanation_auto_accept": account.article_explanation_auto_accept
        }
        if account.article_explanation_auto_accept == auto_accept:
            return ArticleExplanationPreferences(auto_accept)
        account.article_explanation_auto_accept = auto_accept
        account.save(update_fields=("article_explanation_auto_accept", "updated_at"))
        audit_writer(
            action="accounts.article_explanation_preference.change",
            actor_id=account.id,
            target_id=str(account.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after={"article_explanation_auto_accept": auto_accept},
            summary="Change article explanation preference",
        )
    return ArticleExplanationPreferences(auto_accept)


__all__ = [
    "ArticleExplanationPreferenceError",
    "ArticleExplanationPreferences",
    "article_explanation_preferences",
    "change_article_explanation_preferences",
]
