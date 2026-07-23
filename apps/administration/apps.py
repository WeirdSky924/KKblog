from django.apps import AppConfig


class AdministrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.administration"

    def ready(self) -> None:
        from .media_access import register_media_access

        register_media_access()
