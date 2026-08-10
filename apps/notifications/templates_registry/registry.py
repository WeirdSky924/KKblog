import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from html import unescape
from types import MappingProxyType

from django.utils.html import strip_tags

from apps.notifications.markdown import (
    NotificationMarkdownRenderingError,
    render_notification_markdown,
)
from apps.notifications.services.delivery import (
    NOTIFICATION_MARKDOWN_MAX_LENGTH,
    NotificationRejected,
    registered_notification_templates,
)

MessageRenderer = Callable[[Mapping[str, object]], str]
TitleRenderer = Callable[[Mapping[str, object]], str]
_VERSIONED_KEY = re.compile(r"[a-z][a-z0-9_.-]*\.v[1-9][0-9]*\Z")


@dataclass(frozen=True, slots=True)
class NotificationTemplateDefinition:
    key: str
    title: str | TitleRenderer
    render_message: MessageRenderer

    def __post_init__(self) -> None:
        if not _VERSIONED_KEY.fullmatch(self.key):
            raise NotificationRejected("Notification template key must be versioned")
        if isinstance(self.title, str):
            _plain_text(self.title, limit=100)
        elif not callable(self.title):
            raise NotificationRejected("Invalid notification title renderer")
        if not callable(self.render_message):
            raise NotificationRejected("Invalid notification renderer")


@dataclass(frozen=True, slots=True)
class RenderedNotification:
    title: str
    message: str
    message_html: str


_DEFINITIONS: dict[str, NotificationTemplateDefinition] = {}


def _plain_text(value: object, *, limit: int) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= limit
        or "\x00" in value
        or "<" in value
        or ">" in value
        or "://" in value
        or any(
            not character.isprintable() and character not in "\n\t"
            for character in value
        )
    ):
        raise NotificationRejected("Unsafe rendered notification text")
    return value


def _markdown_source(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= NOTIFICATION_MARKDOWN_MAX_LENGTH
        or "\x00" in value
        or any(
            not character.isprintable() and character not in "\n\t"
            for character in value
        )
    ):
        raise NotificationRejected("Unsafe rendered notification Markdown")
    return value


def _message_summary(message_html: str) -> str:
    summary = " ".join(unescape(strip_tags(message_html)).split())
    if not summary:
        raise NotificationRejected("Notification message has no readable content")
    return f"{summary[:237]}..." if len(summary) > 240 else summary


def register_template_definition(
    definition: NotificationTemplateDefinition, *, replace: bool = False
) -> None:
    if definition.key not in registered_notification_templates():
        raise NotificationRejected("Notification schema must be registered first")
    current = _DEFINITIONS.get(definition.key)
    if current is not None and current != definition and not replace:
        raise NotificationRejected("Notification renderer already registered")
    _DEFINITIONS[definition.key] = definition


def registered_template_definitions() -> MappingProxyType:
    return MappingProxyType(_DEFINITIONS)


def render_notification(
    template_key: str, payload: Mapping[str, object]
) -> RenderedNotification:
    definition = _DEFINITIONS.get(template_key)
    schema = registered_notification_templates().get(template_key)
    if definition is None or schema is None:
        raise NotificationRejected("Unknown notification renderer")
    if (
        not isinstance(payload, Mapping)
        or not set(payload) <= schema.allowed_payload_fields
    ):
        raise NotificationRejected("Unknown notification payload field")
    schema.validate_payload(payload)
    try:
        title = (
            definition.title(MappingProxyType(dict(payload)))
            if callable(definition.title)
            else definition.title
        )
        message_source = definition.render_message(MappingProxyType(dict(payload)))
    except NotificationRejected:
        raise
    except (KeyError, TypeError, ValueError):
        raise NotificationRejected("Notification rendering failed") from None
    try:
        message_html = render_notification_markdown(_markdown_source(message_source))
    except NotificationMarkdownRenderingError:
        raise NotificationRejected("Notification rendering failed") from None
    return RenderedNotification(
        title=_plain_text(title, limit=100),
        message=_message_summary(message_html),
        message_html=message_html,
    )
