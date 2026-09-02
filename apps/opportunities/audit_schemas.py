from apps.operations.public import AuditSchema, register_audit_schema


def register_opportunity_audit_schemas() -> None:
    run_fields = frozenset({"run_id", "kind", "state", "reused", "source_id"})
    for action in (
        "opportunities.check.request_source",
        "opportunities.check.request_full",
        "opportunities.check.cancel",
    ):
        register_audit_schema(AuditSchema(action, "opportunity_check_run", run_fields))

    source_fields = frozenset(
        {
            "company_name",
            "source_type",
            "url_host",
            "adapter_key",
            "enabled",
            "publicly_visible",
            "respect_robots_txt",
            "request_interval_seconds",
            "max_pages",
            "max_opportunities",
            "max_duration_seconds",
            "check_state",
            "row_version",
        }
    )
    for action in (
        "opportunities.source.create",
        "opportunities.source.activate",
        "opportunities.source.update",
        "opportunities.source.deactivate",
    ):
        register_audit_schema(AuditSchema(action, "opportunity_source", source_fields))

    opportunity_fields = frozenset(
        {
            "source_id",
            "title",
            "url_host",
            "recruitment_type",
            "verification_status",
            "publication_state",
            "origin",
            "row_version",
        }
    )
    for action in (
        "opportunities.opportunity.create",
        "opportunities.opportunity.update",
        "opportunities.opportunity.verify",
        "opportunities.opportunity.withdraw",
        "opportunities.opportunity.restore",
    ):
        register_audit_schema(AuditSchema(action, "opportunity", opportunity_fields))

    register_audit_schema(
        AuditSchema(
            "opportunities.review.resolve",
            "opportunity_review",
            frozenset({"state"}),
        )
    )
    register_audit_schema(
        AuditSchema(
            "opportunities.review.resolve_batch",
            "opportunity_review_batch",
            frozenset({"count", "scope", "state"}),
        )
    )
    register_audit_schema(
        AuditSchema(
            "opportunities.settings.update",
            "opportunity_settings",
            frozenset(
                {
                    "cities",
                    "statuses",
                    "companies",
                    "recruitment_types",
                    "categories",
                    "cohorts",
                }
            ),
            max_list_items=200,
        )
    )


__all__ = ["register_opportunity_audit_schemas"]
