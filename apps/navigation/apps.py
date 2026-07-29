from django.apps import AppConfig
from django.db.models.signals import post_migrate


def ensure_navigation_defaults(*, sender, **kwargs) -> None:
    del kwargs
    if sender.name != "apps.navigation":
        return
    from .models import (
        NavigationTreeState,
        SiteConfiguration,
        StaticPage,
        TrustedEmbedSource,
    )

    NavigationTreeState.objects.get_or_create(pk=1, defaults={"row_version": 1})
    SiteConfiguration.objects.get_or_create(pk=1)
    for page_type in StaticPage.PageType:
        StaticPage.objects.get_or_create(page_type=page_type)
    TrustedEmbedSource.objects.get_or_create(
        source_key="bilibili",
        defaults={
            "display_name": "Bilibili 视频",
            "host_pattern": "www.bilibili.com/video/BV...",
            "enabled": True,
        },
    )


class NavigationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.navigation"

    def ready(self) -> None:
        from .audit_schemas import register_navigation_audit_schemas

        register_navigation_audit_schemas()
        post_migrate.connect(
            ensure_navigation_defaults,
            sender=self,
            dispatch_uid="navigation.ensure_defaults",
        )
