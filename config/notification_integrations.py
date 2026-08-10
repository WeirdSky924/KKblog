from apps.media.public import RenderingError, render_markdown
from apps.notifications.markdown import NotificationMarkdownRenderingError


def render_notification_markdown(source: str) -> str:
    try:
        return render_markdown(source).html
    except RenderingError:
        raise NotificationMarkdownRenderingError(
            "Notification Markdown could not be rendered"
        ) from None


__all__ = ["render_notification_markdown"]
