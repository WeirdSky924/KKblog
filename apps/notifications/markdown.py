from collections.abc import Callable

from django.conf import settings
from django.utils.module_loading import import_string


class NotificationMarkdownRenderingError(ValueError):
    pass


def render_notification_markdown(source: str) -> str:
    provider_path = getattr(settings, "NOTIFICATION_MARKDOWN_RENDERER_PROVIDER", "")
    if not isinstance(provider_path, str) or not provider_path:
        raise NotificationMarkdownRenderingError(
            "Notification Markdown renderer is not configured"
        )
    provider = import_string(provider_path)
    if not isinstance(provider, Callable):
        raise NotificationMarkdownRenderingError(
            "Notification Markdown renderer is invalid"
        )
    try:
        rendered = provider(source)
    except NotificationMarkdownRenderingError:
        raise
    except (TypeError, ValueError):
        raise NotificationMarkdownRenderingError(
            "Notification Markdown could not be rendered"
        ) from None
    if not isinstance(rendered, str) or not rendered:
        raise NotificationMarkdownRenderingError(
            "Notification Markdown renderer returned invalid HTML"
        )
    return rendered


__all__ = [
    "NotificationMarkdownRenderingError",
    "render_notification_markdown",
]
