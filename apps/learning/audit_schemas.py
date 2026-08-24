from apps.operations.public import AuditSchema, register_audit_schema

_QUOTA_FIELDS = frozenset(
    {
        "daily_uploads",
        "pending_reviews",
        "daily_generations",
        "concurrent_model_runs",
        "unpurged_banks",
        "max_questions_per_volume",
        "row_version",
    }
)
_ADMIN_DOCUMENT_FIELDS = frozenset(
    {"state", "admin_lock_reason", "deletion_actor", "row_version"}
)
_ADMIN_BANK_FIELDS = frozenset(
    {"visibility", "admin_lock_reason", "deletion_actor", "row_version"}
)
_APPEAL_FIELDS = frozenset({"state", "row_version"})
_API_FIELDS = frozenset(
    {
        "enabled",
        "cors_mode",
        "cors_origins",
        "minute_limit",
        "daily_limit",
        "row_version",
    }
)
_GENERATION_RESET_FIELDS = frozenset(
    {"usage_date", "account_count", "generations_reset"}
)


def register_learning_audit_schemas() -> None:
    register_audit_schema(
        AuditSchema(
            "learning.quota.site.update",
            "learning_quota_policy",
            _QUOTA_FIELDS,
        )
    )
    for action in ("hide", "restore", "delete"):
        register_audit_schema(
            AuditSchema(
                f"learning.document.admin.{action}",
                "knowledge_document",
                _ADMIN_DOCUMENT_FIELDS,
            )
        )
        register_audit_schema(
            AuditSchema(
                f"learning.bank.admin.{action}",
                "question_bank",
                _ADMIN_BANK_FIELDS,
            )
        )
    register_audit_schema(
        AuditSchema(
            "learning.appeal.review",
            "learning_appeal",
            _APPEAL_FIELDS,
        )
    )
    register_audit_schema(
        AuditSchema(
            "learning.quota.account.update",
            "learning_account_quota_override",
            _QUOTA_FIELDS,
        )
    )
    register_audit_schema(
        AuditSchema(
            "learning.question_limit.update",
            "learning_quota_policy",
            _QUOTA_FIELDS,
        )
    )
    register_audit_schema(
        AuditSchema(
            "learning.question_bank_api.update",
            "learning_question_bank_api_configuration",
            _API_FIELDS,
        )
    )
    register_audit_schema(
        AuditSchema(
            "learning.quota.daily_generation.reset",
            "learning_daily_usage",
            _GENERATION_RESET_FIELDS,
        )
    )


__all__ = ["register_learning_audit_schemas"]
