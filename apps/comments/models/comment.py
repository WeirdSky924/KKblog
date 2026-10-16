from django.db import models
from django.utils import timezone

from apps.core.ids import new_ulid


class Comment(models.Model):
    class AuthorKind(models.TextChoices):
        ANONYMOUS = "ANONYMOUS", "访客"
        ACCOUNT = "ACCOUNT", "账户"
        DELETED_ACCOUNT = "DELETED_ACCOUNT", "已注销账户"

    class State(models.TextChoices):
        BUFFERED = "BUFFERED", "缓冲中"
        VISIBLE = "VISIBLE", "已公开"
        DELETED = "DELETED", "已删除"

    class DeletedByKind(models.TextChoices):
        SELF = "SELF", "本人"
        OWNER = "OWNER", "内容所有者"
        ADMIN = "ADMIN", "管理员"
        REPORT = "REPORT", "举报裁决"

    class GuestbookFlag(models.TextChoices):
        NONE = "", "无标记"
        READ = "READ", "阅"
        NO = "NO", "否"
        DONE = "DONE", "毕"

    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    thread = models.ForeignKey(
        "comments.DiscussionThread",
        related_name="comments",
        on_delete=models.CASCADE,
        db_constraint=False,
    )
    parent = models.ForeignKey(
        "self",
        related_name="direct_replies",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_constraint=False,
    )
    root = models.ForeignKey(
        "self",
        related_name="thread_replies",
        on_delete=models.CASCADE,
        db_constraint=False,
    )
    author = models.ForeignKey(
        "accounts.Account",
        related_name="comments_authored",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
    )
    author_kind = models.CharField(max_length=24, choices=AuthorKind.choices)
    body = models.CharField(max_length=100)
    state = models.CharField(
        max_length=16,
        choices=State.choices,
        default=State.BUFFERED,
    )
    visible_at = models.DateTimeField()
    depth = models.PositiveIntegerField(default=0)
    reply_count = models.PositiveBigIntegerField(default=0)
    client_ip = models.GenericIPAddressField(protocol="both", unpack_ipv4=True)
    deleted_by_kind = models.CharField(
        max_length=16,
        choices=DeletedByKind.choices,
        null=True,
        blank=True,
    )
    deletion_reason = models.CharField(max_length=200, null=True, blank=True)
    guestbook_hidden = models.BooleanField(default=False)
    guestbook_flag = models.CharField(
        max_length=4,
        choices=GuestbookFlag.choices,
        default=GuestbookFlag.NONE,
    )
    guestbook_hidden_at = models.DateTimeField(null=True, blank=True, editable=False)
    guestbook_hidden_by = models.ForeignKey(
        "accounts.Account",
        related_name="guestbook_comments_hidden",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        db_constraint=False,
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "comment"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id__regex=r"^[0-9A-HJKMNP-TV-Z]{26}$"),
                name="comment_id_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(author_kind="ACCOUNT", author__isnull=False)
                    | models.Q(
                        author_kind__in=("ANONYMOUS", "DELETED_ACCOUNT"),
                        author__isnull=True,
                    )
                ),
                name="comment_author_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        parent__isnull=True,
                        root=models.F("id"),
                        depth=0,
                    )
                    | models.Q(parent__isnull=False, depth__gte=1)
                ),
                name="comment_tree_root_shape",
            ),
            models.CheckConstraint(
                condition=models.Q(visible_at__gte=models.F("created_at")),
                name="comment_visible_at_order",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state="DELETED",
                        body="",
                        deleted_by_kind__isnull=False,
                    )
                    | (
                        ~models.Q(state="DELETED")
                        & ~models.Q(body="")
                        & models.Q(
                            deleted_by_kind__isnull=True,
                            deletion_reason__isnull=True,
                        )
                    )
                ),
                name="comment_deletion_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("thread", "state", "created_at", "id"),
                condition=models.Q(parent__isnull=True),
                name="comment_top_created_idx",
            ),
            models.Index(
                fields=("parent", "created_at", "id"),
                name="comment_reply_created_idx",
            ),
            models.Index(
                fields=("thread", "-reply_count", "created_at", "id"),
                condition=models.Q(parent__isnull=True),
                name="comment_top_hot_idx",
            ),
            models.Index(
                fields=("visible_at", "id"),
                condition=models.Q(state="BUFFERED"),
                name="comment_buffer_due_idx",
            ),
            models.Index(
                fields=("thread", "guestbook_hidden", "-created_at", "-id"),
                condition=models.Q(
                    parent__isnull=True,
                    state="VISIBLE",
                ),
                name="comment_guestbook_public_idx",
            ),
            models.Index(
                fields=("thread", "author", "created_at", "id"),
                condition=models.Q(parent__isnull=True),
                name="comment_top_author_day_idx",
            ),
            models.Index(
                fields=("thread", "created_at"),
                condition=models.Q(parent__isnull=True),
                name="comment_top_daily_idx",
            ),
        ]
