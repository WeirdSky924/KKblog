from django.conf import settings


def analytics_tracking(_request) -> dict[str, object]:
    enabled = bool(
        getattr(settings, "ANALYTICS_ENABLED", False)
        and getattr(settings, "ANALYTICS_WEBSITE_ID", "")
    )
    return {
        "analytics_tracking": {
            "enabled": enabled,
            "script_path": "/analytics/script.js",
            "website_id": settings.ANALYTICS_WEBSITE_ID if enabled else "",
        }
    }
