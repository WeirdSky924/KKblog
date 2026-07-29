from apps.operations.public import AuditSchema, register_audit_schema


def register_navigation_audit_schemas() -> None:
    fields = frozenset(
        {
            "label",
            "node_type",
            "parent_id",
            "position",
            "depth",
            "hidden",
            "target_ref",
            "row_version",
            "deleted",
        }
    )
    for action in (
        "navigation.node.create",
        "navigation.node.edit",
        "navigation.node.visibility",
        "navigation.node.move",
        "navigation.node.delete",
    ):
        register_audit_schema(AuditSchema(action, "navigation_node", fields))

    register_audit_schema(
        AuditSchema(
            "navigation.site_configuration.update",
            "site_configuration",
            frozenset(
                {
                    "site_name",
                    "site_description",
                    "copyright_text",
                    "registration_enabled",
                    "article_text_limit_bytes",
                    "logo_asset_id",
                    "backup_destination",
                    "row_version",
                }
            ),
        )
    )
    register_audit_schema(
        AuditSchema(
            "navigation.static_page.update",
            "static_page",
            frozenset(
                {
                    "page_type",
                    "format",
                    "published",
                    "source_digest",
                    "row_version",
                }
            ),
        )
    )
    friend_fields = frozenset(
        {
            "name",
            "url_host",
            "position",
            "logo_asset_id",
            "row_version",
            "deleted",
        }
    )
    for action in (
        "navigation.friend_link.create",
        "navigation.friend_link.update",
        "navigation.friend_link.reorder",
        "navigation.friend_link.delete",
    ):
        register_audit_schema(AuditSchema(action, "friend_link", friend_fields))
    register_audit_schema(
        AuditSchema(
            "navigation.trusted_source.update",
            "trusted_embed_source",
            frozenset({"source_key", "enabled", "row_version"}),
        )
    )


__all__ = ["register_navigation_audit_schemas"]
