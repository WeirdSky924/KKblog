import re

from django.conf import settings
from django.core.mail import send_mail

from apps.operations.services.alerts import OperationalEmailMessage

_RESEND_KEY = re.compile(r"re_[A-Za-z0-9_-]{20,}\Z")
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class OperationalEmailConfigurationError(RuntimeError):
    pass


class OperationalEmailDeliveryError(RuntimeError):
    pass


def _configuration_error(name: str) -> OperationalEmailConfigurationError:
    return OperationalEmailConfigurationError(
        f"Invalid operational email configuration: {name}"
    )


def _validate_mailpit() -> None:
    if settings.ADMIN_EMAIL != "admin@kaj.test":
        raise _configuration_error("ADMIN_EMAIL")
    if settings.DEFAULT_FROM_EMAIL != "no-reply@kaj.test":
        raise _configuration_error("DEFAULT_FROM_EMAIL")
    if settings.EMAIL_HOST not in _LOOPBACK_HOSTS:
        raise _configuration_error("EMAIL_HOST")
    if (
        not isinstance(settings.EMAIL_PORT, int)
        or not 1_024 <= settings.EMAIL_PORT <= 65_535
    ):
        raise _configuration_error("EMAIL_PORT")
    if settings.EMAIL_USE_TLS:
        raise _configuration_error("EMAIL_USE_TLS")


def _validate_resend() -> None:
    password = getattr(settings, "EMAIL_HOST_PASSWORD", "")
    if not isinstance(password, str) or not _RESEND_KEY.fullmatch(password):
        raise _configuration_error("EMAIL_HOST_PASSWORD")
    if settings.ADMIN_EMAIL.casefold().endswith((".test", "@localhost")):
        raise _configuration_error("ADMIN_EMAIL")
    if settings.DEFAULT_FROM_EMAIL.casefold().endswith((".test", "@localhost")):
        raise _configuration_error("DEFAULT_FROM_EMAIL")
    if settings.EMAIL_HOST != "smtp.resend.com":
        raise _configuration_error("EMAIL_HOST")
    if getattr(settings, "EMAIL_HOST_USER", "") != "resend":
        raise _configuration_error("EMAIL_HOST_USER")
    if settings.EMAIL_PORT != 587 or not settings.EMAIL_USE_TLS:
        raise _configuration_error("EMAIL_TRANSPORT")


def send_configured_operational_email(message: OperationalEmailMessage) -> None:
    provider = getattr(settings, "OPERATIONAL_EMAIL_PROVIDER", "")
    if provider == "mailpit":
        _validate_mailpit()
    elif provider == "resend":
        _validate_resend()
    else:
        raise _configuration_error("OPERATIONAL_EMAIL_PROVIDER")
    if not isinstance(message, OperationalEmailMessage):
        raise TypeError("Operational email message is invalid")
    sent = send_mail(
        subject=message.subject,
        message=message.body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[settings.ADMIN_EMAIL],
        fail_silently=False,
    )
    if sent != 1:
        raise OperationalEmailDeliveryError("Operational email was not accepted")
