from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.paginator import Paginator

from ..models import Comment
from ..ports import CommentAccountPolicy, default_comment_account_policy
from ..services.threads import sync_guestbook_thread


class GuestbookAdminQueryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GuestbookAdminItem:
    id: str
    body: str
    state: str
    hidden: bool
    flag: str
    author_id: UUID | None
    author_kind: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class GuestbookAdminPage:
    items: tuple[GuestbookAdminItem, ...]
    page_number: int
    page_size: int
    total_items: int
    total_pages: int
    has_previous: bool
    has_next: bool
    board_daily_limit: int
    account_daily_limit: int
    quota_version: int


def _require_admin(actor_id, account_policy: CommentAccountPolicy) -> UUID:
    try:
        actor = UUID(str(actor_id))
    except (TypeError, ValueError):
        raise PermissionError from None
    if not account_policy.is_administrator(actor):
        raise PermissionError
    return actor


def guestbook_admin_page(
    *,
    actor_id,
    page: int = 1,
    page_size: int = 20,
    account_policy: CommentAccountPolicy | None = None,
) -> GuestbookAdminPage:
    accounts = account_policy or default_comment_account_policy()
    _require_admin(actor_id, accounts)
    if isinstance(page, bool) or page < 1 or page_size not in {10, 20, 50}:
        raise GuestbookAdminQueryError("留言板管理分页参数无效。")
    thread = sync_guestbook_thread(account_policy=accounts)
    paginator = Paginator(
        Comment.objects.filter(
            thread=thread,
            parent__isnull=True,
        ).order_by("-created_at", "-id"),
        page_size,
    )
    selected = paginator.get_page(page)
    items = tuple(
        GuestbookAdminItem(
            id=row.id,
            body=row.body,
            state=row.state,
            hidden=row.guestbook_hidden,
            flag=row.guestbook_flag,
            author_id=row.author_id,
            author_kind=row.author_kind,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in selected.object_list
    )
    return GuestbookAdminPage(
        items=items,
        page_number=selected.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
        board_daily_limit=thread.guestbook_daily_limit,
        account_daily_limit=thread.guestbook_account_daily_limit,
        quota_version=thread.guestbook_quota_version,
    )
