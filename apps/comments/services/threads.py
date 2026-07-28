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
        "settings_revision_id": target.revision_id,
    }
    with transaction.atomic():
        thread, created = DiscussionThread.objects.select_for_update().get_or_create(
            target_type=DiscussionTargetType.ARTICLE,
            target_id=target.article_id,
            defaults=defaults,
        )
        if not created:
            update_fields = []
            if thread.owner_id != target.owner_id:
                thread.owner_id = target.owner_id
                update_fields.append("owner")
            if thread.settings_revision_id != target.revision_id:
                thread.comments_enabled = target.comments_enabled
                thread.view_login_required = target.view_login_required
                thread.post_login_required = target.post_login_required
                thread.settings_revision_id = target.revision_id
                update_fields.extend(
                    (
                        "comments_enabled",
                        "view_login_required",
                        "post_login_required",
                        "settings_revision_id",
                    )
                )
            if update_fields:
                thread.save(update_fields=(*update_fields, "updated_at"))
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
