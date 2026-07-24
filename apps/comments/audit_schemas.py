from apps.operations.public import AuditSchema, register_audit_schema


def register_comment_audit_schemas() -> None:
    register_audit_schema(
        AuditSchema(
            "comments.comment.admin_delete",
            "comment",
            frozenset(
                {
                    "author_kind",
                    "deleted_by_kind",
                    "image_count",
                    "reason_provided",
                    "state",
                }
            ),
        )
    )
    register_audit_schema(
        AuditSchema(
            "comments.guestbook.settings_update",
            "discussion_thread",
            frozenset({"comments_enabled", "post_login_required"}),
        )
    )
