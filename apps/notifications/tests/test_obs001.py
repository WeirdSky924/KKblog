import uuid

import pytest
from django.apps import apps as django_apps
from django.db import IntegrityError

from apps.notifications.models import NotificationReceipt
from apps.notifications.queries import notification_for_recipient
from apps.notifications.services.delivery import (
    NotificationRejected,
    NotificationTemplateSchema,
    deliver_notification,
    register_notification_template,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def recipients():
    account_model = django_apps.get_model("accounts", "Account")
    return [
        account_model.objects.create_account(
            email=f"notify-{number}@kaj.test", password="Valid-password-1"
        )
        for number in range(2)
    ]


@pytest.fixture(autouse=True)
def template_schema() -> None:
    register_notification_template(
        NotificationTemplateSchema(
            key="test.safe",
            target_type="account",
            allowed_payload_fields=frozenset({"state", "reason_code"}),
        ),
        replace=True,
    )


def test_receipt_pair_is_unique(recipients) -> None:
    notification = deliver_notification(
        template_key="test.safe",
        recipient_ids=[recipient.id for recipient in recipients],
        target_id=str(recipients[0].id),
        payload={"state": "changed"},
    )
    with pytest.raises(IntegrityError):
        NotificationReceipt.objects.create(
            notification=notification, recipient=recipients[0]
        )


def test_other_recipient_cannot_read_notification(recipients) -> None:
    notification = deliver_notification(
        template_key="test.safe",
        recipient_ids=[recipients[0].id],
        target_id=str(recipients[0].id),
        payload={"state": "changed"},
    )
    assert (
        notification_for_recipient(
            notification_id=notification.id, recipient_id=recipients[0].id
        ).notification_id
        == notification.id
    )
    with pytest.raises(PermissionError):
        notification_for_recipient(
            notification_id=notification.id, recipient_id=recipients[1].id
        )


def test_dedupe_key_returns_one_notification_and_receipt(recipients) -> None:
    kwargs = {
        "template_key": "test.safe",
        "recipient_ids": [recipients[0].id],
        "target_id": str(recipients[0].id),
        "payload": {"state": "changed"},
        "dedupe_key": "test:account:changed:1",
    }
    first = deliver_notification(**kwargs)
    second = deliver_notification(**kwargs)
    assert first.id == second.id
    assert NotificationReceipt.objects.count() == 1


@pytest.mark.parametrize(
    "template_key,payload",
    [
        ("unknown.template", {"state": "changed"}),
        ("test.safe", {"html": "<script>"}),
        ("test.safe", {"url": "https://attacker.invalid"}),
        ("test.safe", {"state": "changed", "token": "secret"}),
        ("test.safe", {"state": {"nested": "body"}}),
    ],
)
def test_unknown_template_or_dangerous_payload_is_rejected(
    recipients, template_key, payload
) -> None:
    with pytest.raises(NotificationRejected):
        deliver_notification(
            template_key=template_key,
            recipient_ids=[recipients[0].id],
            target_id=str(uuid.uuid4()),
            payload=payload,
        )
