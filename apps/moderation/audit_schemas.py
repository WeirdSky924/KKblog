from apps.operations.public import AuditSchema, register_audit_schema


def register_moderation_audit_schemas() -> None:
    register_audit_schema(
        AuditSchema(
            "moderation.report.review",
            "report",
            frozenset(
                {
                    "comment_changed",
                    "image_count",
                    "outcome",
                    "reason_provided",
                    "snapshot_created",
                    "state",
                }
            ),
        )
    )
    register_audit_schema(
        AuditSchema(
            "moderation.report.final_review",
            "report",
            frozenset(
                {
                    "appeal_state",
                    "basis_outcome",
                    "comment_changed",
                    "outcome",
                    "reason_provided",
                    "recovery_status",
                    "snapshot_destroyed",
                    "state",
                }
            ),
        )
    )
