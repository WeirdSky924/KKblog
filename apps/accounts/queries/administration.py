from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.paginator import Paginator
from django.db.models import Prefetch, Q

from apps.accounts.models import Account, RoleAssignment

ADMIN_ACCOUNT_STATUSES = (Account.Status.ACTIVE, Account.Status.DISABLED)
ADMIN_ACCOUNT_PAGE_SIZES = frozenset({20, 50, 100})


class AccountAdministrationQueryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AdminAccountItem:
    account_id: UUID
    email: str
    nickname: str | None
    status: str
    roles: tuple[str, ...]
    created_at: datetime

    @property
    def display_name(self) -> str:
        return self.nickname or self.email.split("@", 1)[0]

    @property
    def is_author(self) -> bool:
        return RoleAssignment.Role.AUTHOR in self.roles

    @property
    def is_administrator(self) -> bool:
        return RoleAssignment.Role.ADMINISTRATOR in self.roles


@dataclass(frozen=True, slots=True)
class AdminAccountPage:
    items: tuple[AdminAccountItem, ...]
    keyword: str
    selected_status: str
    page_number: int
    page_size: int
    total_items: int
    total_pages: int
    has_previous: bool
    has_next: bool


def _administrator(value) -> UUID:
    try:
        actor_id = UUID(str(value))
    except (TypeError, ValueError):
        raise PermissionError("Administrator access required") from None
    if not RoleAssignment.objects.filter(
        account_id=actor_id,
        account__status=Account.Status.ACTIVE,
        role=RoleAssignment.Role.ADMINISTRATOR,
    ).exists():
        raise PermissionError("Administrator access required")
    return actor_id


def _status(value: str) -> str:
    normalized = value.strip().upper()
    if normalized and normalized not in ADMIN_ACCOUNT_STATUSES:
        raise AccountAdministrationQueryError("账户状态筛选无效")
    return normalized


def _page_number(value) -> int:
    if isinstance(value, bool):
        return 1
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _item(account: Account) -> AdminAccountItem:
    return AdminAccountItem(
        account_id=account.id,
        email=account.email,
        nickname=account.nickname,
        status=account.status,
        roles=tuple(sorted(item.role for item in account.roles.all())),
        created_at=account.created_at,
    )


def admin_account_page(
    *,
    actor_id,
    keyword: str = "",
    status: str = "",
    page: int = 1,
    page_size: int = 20,
) -> AdminAccountPage:
    _administrator(actor_id)
    if not isinstance(keyword, str) or len(keyword) > 254:
        raise AccountAdministrationQueryError("搜索条件无效")
    selected_status = _status(status)
    if isinstance(page_size, bool) or page_size not in ADMIN_ACCOUNT_PAGE_SIZES:
        raise AccountAdministrationQueryError("分页数量无效")
    query = keyword.strip()
    queryset = Account.objects.order_by("-created_at", "id")
    if query:
        queryset = queryset.filter(
            Q(email__icontains=query) | Q(nickname__icontains=query)
        )
    if selected_status:
        queryset = queryset.filter(status=selected_status)
    queryset = queryset.prefetch_related(
        Prefetch("roles", queryset=RoleAssignment.objects.order_by("role"))
    )
    paginator = Paginator(queryset, page_size)
    selected = paginator.get_page(_page_number(page))
    return AdminAccountPage(
        items=tuple(_item(account) for account in selected.object_list),
        keyword=query,
        selected_status=selected_status,
        page_number=selected.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )


def admin_account_detail(*, actor_id, account_id) -> AdminAccountItem:
    _administrator(actor_id)
    try:
        identity = UUID(str(account_id))
    except (TypeError, ValueError):
        raise AccountAdministrationQueryError("账户不存在") from None
    try:
        account = Account.objects.prefetch_related(
            Prefetch("roles", queryset=RoleAssignment.objects.order_by("role"))
        ).get(pk=identity)
    except Account.DoesNotExist:
        raise AccountAdministrationQueryError("账户不存在") from None
    return _item(account)


__all__ = [
    "ADMIN_ACCOUNT_PAGE_SIZES",
    "ADMIN_ACCOUNT_STATUSES",
    "AccountAdministrationQueryError",
    "AdminAccountItem",
    "AdminAccountPage",
    "admin_account_detail",
    "admin_account_page",
]
