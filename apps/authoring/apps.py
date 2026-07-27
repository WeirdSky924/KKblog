from django.apps import AppConfig


class AuthoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.authoring"
    verbose_name = "作者工作台"

    def ready(self) -> None:
        from .media_access import register_media_access

        register_media_access()
