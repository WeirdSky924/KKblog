import pytest
from django.test import override_settings

from apps.operations.services.alerts import OperationalEmailMessage
from config.operational_email import (
    OperationalEmailConfigurationError,
    send_configured_operational_email,
)


@override_settings(
    ADMIN_EMAIL="admin@kaj.test",
    DEFAULT_FROM_EMAIL="no-reply@kaj.test",
    EMAIL_HOST="172.17.0.4",
    EMAIL_PORT=1025,
    EMAIL_USE_TLS=False,
    EMAIL_USE_SSL=False,
    OPERATIONAL_EMAIL_PROVIDER="mailpit",
)
def test_mailpit_accepts_isolated_private_container_host(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "config.operational_email.send_mail",
        lambda **kwargs: calls.append(kwargs) or 1,
    )

    send_configured_operational_email(
        OperationalEmailMessage(
            delivery_id="window-1",
            subject="Kaj 运维测试",
            body="mailpit body",
        )
    )

    assert len(calls) == 1
    assert calls[0]["recipient_list"] == ["admin@kaj.test"]


@override_settings(
    ADMIN_EMAIL="admin@kaj.test",
    DEFAULT_FROM_EMAIL="no-reply@kaj.test",
    EMAIL_HOST="203.0.113.10",
    EMAIL_PORT=1025,
    EMAIL_USE_TLS=False,
    EMAIL_USE_SSL=False,
    OPERATIONAL_EMAIL_PROVIDER="mailpit",
)
def test_mailpit_rejects_public_host(monkeypatch) -> None:
    monkeypatch.setattr("config.operational_email.send_mail", lambda **_: 1)

    with pytest.raises(OperationalEmailConfigurationError, match="EMAIL_HOST"):
        send_configured_operational_email(
            OperationalEmailMessage(
                delivery_id="window-2",
                subject="Kaj 运维测试",
                body="mailpit body",
            )
        )
