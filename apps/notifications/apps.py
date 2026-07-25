from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"

    def ready(self) -> None:
        from apps.notifications.templates_registry import register_builtin_templates

        register_builtin_templates()
