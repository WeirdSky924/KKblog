from django.apps import AppConfig


class OperationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.operations"

    def ready(self) -> None:
        from apps.operations import audit_schemas

        audit_schemas.register_builtin_audit_schemas()
