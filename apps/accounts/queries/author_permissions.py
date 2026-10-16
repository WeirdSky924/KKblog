from uuid import UUID

from apps.accounts.models import Account


def author_permission_request_submitted(account_id: UUID | str | None) -> bool:
    try:
        identity = UUID(str(account_id))
    except (TypeError, ValueError):
        return False
    return Account.objects.filter(
        pk=identity,
        author_permission_requested_at__isnull=False,
    ).exists()


__all__ = ["author_permission_request_submitted"]
