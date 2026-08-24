from apps.operations.public import AuditSchema, register_audit_schema


def register_agent_audit_schemas() -> None:
    endpoint_fields = frozenset(
        {
            "protocol",
            "authentication_mode",
            "authentication_reference_present",
            "model_configured",
            "reasoning_effort",
            "thinking_budget",
            "enabled",
            "context_window_units",
            "max_output_units",
            "per_run_unit_limit",
            "request_timeout_seconds",
            "concurrency_limit",
            "daily_unit_limit",
            "row_version",
        }
    )
    for action in ("agents.endpoint.create", "agents.endpoint.update"):
        register_audit_schema(AuditSchema(action, "agent_endpoint", endpoint_fields))
    register_audit_schema(
        AuditSchema(
            "agents.endpoint_check.request",
            "agent_endpoint_check",
            frozenset(
                {
                    "endpoint_id",
                    "endpoint_row_version",
                    "reservation_units",
                    "state",
                }
            ),
        )
    )

    profile_fields = frozenset(
        {
            "profile_key",
            "purpose",
            "endpoint_id",
            "schema_key",
            "enabled",
            "current_prompt_sequence",
            "row_version",
        }
    )
    for action in (
        "agents.profile.create",
        "agents.profile.update",
        "agents.profile.enabled",
        "agents.prompt.save",
        "agents.prompt.switch",
    ):
        register_audit_schema(AuditSchema(action, "agent_profile", profile_fields))

    register_audit_schema(
        AuditSchema(
            "agents.token_usage.reset",
            "agent_token_usage",
            frozenset(
                {
                    "scope",
                    "endpoint_id",
                    "before_units",
                    "after_units",
                    "active_reservation_count",
                    "adjustment_count",
                }
            ),
        )
    )
    limit_fields = frozenset({"site_daily_units", "endpoint_count", "row_version"})
    for action in (
        "agents.token_limits.update",
        "agents.token_limits.restore_defaults",
    ):
        register_audit_schema(AuditSchema(action, "agent_site_policy", limit_fields))


__all__ = ["register_agent_audit_schemas"]
