from django.apps import AppConfig


class ContentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.content"

    def ready(self) -> None:
        from .audit_schemas import register_content_audit_schemas
        from .media_access import register_media_access

        register_content_audit_schemas()
        register_media_access()
