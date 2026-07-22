from apps.operations.services.audit import AuditSchema, register_audit_schema


def register_builtin_audit_schemas() -> None:
    schemas = (
        AuditSchema(
            "accounts.invite.generate",
            "invite_batch",
            frozenset({"count", "validity_days", "invite_ids"}),
        ),
        AuditSchema(
            "accounts.invite.revoke",
            "invite_code",
            frozenset({"state"}),
        ),
        AuditSchema(
            "accounts.restriction.clear",
            "account_restriction",
            frozenset({"restriction_kind"}),
        ),
        AuditSchema(
            "accounts.ip_block.block",
            "ip_block",
            frozenset({"active", "note_present"}),
        ),
        AuditSchema(
            "accounts.ip_block.unblock",
            "ip_block",
            frozenset({"active"}),
        ),
        AuditSchema(
            "accounts.role.set",
            "account",
            frozenset({"roles", "status"}),
        ),
        AuditSchema(
            "accounts.account.status",
            "account",
            frozenset({"status", "roles"}),
        ),
        AuditSchema(
            "accounts.account.delete",
            "account",
            frozenset({"status", "roles", "deletion_id", "disposition"}),
        ),
    )
    for schema in schemas:
        register_audit_schema(schema)
