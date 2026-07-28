from dataclasses import dataclass

from apps.accounts.public import (
    AdminAccountItem,
    AdminAccountPage,
    admin_account_detail,
    admin_account_page,
)
from apps.content.public import admin_author_article_counts


@dataclass(frozen=True, slots=True)
class AdminUserRow:
    account: AdminAccountItem
    article_count: int

    @property
    def can_manage(self) -> bool:
        return not self.account.is_administrator


@dataclass(frozen=True, slots=True)
class AdminUsersPresentation:
    page: AdminAccountPage
    rows: tuple[AdminUserRow, ...]


def admin_users_presentation(
    *, actor_id, keyword: str, status: str, page: int
) -> AdminUsersPresentation:
    account_page = admin_account_page(
        actor_id=actor_id,
        keyword=keyword,
        status=status,
        page=page,
    )
    counts = {
        item.account_id: item.article_count
        for item in admin_author_article_counts(
            actor_id=actor_id,
            account_ids=(item.account_id for item in account_page.items),
        )
    }
    return AdminUsersPresentation(
        page=account_page,
        rows=tuple(
            AdminUserRow(account, counts.get(account.account_id, 0))
            for account in account_page.items
        ),
    )


def admin_user_target(*, actor_id, account_id) -> AdminUserRow:
    account = admin_account_detail(actor_id=actor_id, account_id=account_id)
    count = admin_author_article_counts(
        actor_id=actor_id,
        account_ids=(account.account_id,),
    )[0]
    return AdminUserRow(account, count.article_count)


__all__ = [
    "AdminUserRow",
    "AdminUsersPresentation",
    "admin_user_target",
    "admin_users_presentation",
]
