from django.apps import AppConfig


class AgentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.agents"

    def ready(self) -> None:
        from .audit_schemas import register_agent_audit_schemas

        register_agent_audit_schemas()
