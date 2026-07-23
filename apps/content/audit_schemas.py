from apps.operations.public import AuditSchema, register_audit_schema


def register_content_audit_schemas() -> None:
    fields = frozenset({"name", "normalized_name", "deleted"})
    for action in (
        "content.section.create",
        "content.section.rename",
        "content.section.delete",
    ):
        register_audit_schema(AuditSchema(action, "section", fields))
    tag_fields = frozenset(
        {
            "name",
            "normalized_name",
            "state",
            "outcome",
            "affected_count",
            "restored_count",
            "conflict_count",
        }
    )
    for action in (
        "content.tag.create",
        "content.tag.review",
        "content.tag.delete",
        "content.tag.restore",
    ):
        register_audit_schema(AuditSchema(action, "tag", tag_fields))
    article_deletion_fields = frozenset(
        {
            "administrative",
            "deleted_at",
            "publication_state",
            "purge_after",
            "restored",
        }
    )
    for action in (
        "content.article.delete",
        "content.article.restore",
    ):
        register_audit_schema(AuditSchema(action, "article", article_deletion_fields))
