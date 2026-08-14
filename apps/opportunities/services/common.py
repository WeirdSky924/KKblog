from uuid import UUID

from apps.accounts.public import is_administrator


class OpportunityCommandError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.safe_message = message
        super().__init__(message)


def require_administrator(value) -> UUID:
    try:
        actor_id = UUID(str(value))
    except (TypeError, ValueError):
        raise OpportunityCommandError(
            "opportunities.admin_required.v1",
            "只有管理员可以管理工作机会。",
        ) from None
    if not is_administrator(actor_id):
        raise OpportunityCommandError(
            "opportunities.admin_required.v1",
            "只有管理员可以管理工作机会。",
        )
    return actor_id


def uuid_value(value, *, code: str, message: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise OpportunityCommandError(code, message) from None


__all__ = ["OpportunityCommandError", "require_administrator", "uuid_value"]
