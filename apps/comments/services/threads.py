from django.db import transaction

from apps.content.public import ArticleCommentTarget, article_comment_target

from ..models import DiscussionThread
from ..ports import CommentAccountPolicy, default_comment_account_policy
from ..targets import GUESTBOOK_TARGET_ID, DiscussionTargetType


class GuestbookUnavailableError(RuntimeError):
    pass


def sync_article_thread(
    *, actor_id, article_id: str
) -> tuple[DiscussionThread, ArticleCommentTarget]:
    target = article_comment_target(actor_id=actor_id, article_id=article_id)
    defaults = {
        "owner_id": target.owner_id,
        "comments_enabled": target.comments_enabled,
        "view_login_required": target.view_login_required,
        "post_login_required": target.post_login_required,
    }
    with transaction.atomic():
        thread, _ = DiscussionThread.objects.update_or_create(
            target_type=DiscussionTargetType.ARTICLE,
            target_id=target.article_id,
            defaults=defaults,
        )
    return thread, target


def sync_guestbook_thread(
    *, account_policy: CommentAccountPolicy | None = None
) -> DiscussionThread:
    accounts = account_policy or default_comment_account_policy()
    owner_id = accounts.administrator_id()
    if owner_id is None:
        raise GuestbookUnavailableError("Active administrator is unavailable")
    with transaction.atomic():
        thread, created = DiscussionThread.objects.get_or_create(
            target_type=DiscussionTargetType.GUESTBOOK,
            target_id=GUESTBOOK_TARGET_ID,
            defaults={
                "owner_id": owner_id,
                "comments_enabled": True,
                "view_login_required": False,
                "post_login_required": False,
            },
        )
        if not created and thread.owner_id != owner_id:
            thread.owner_id = owner_id
            thread.save(update_fields=("owner", "updated_at"))
    return thread
