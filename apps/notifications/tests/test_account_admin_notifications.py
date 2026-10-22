import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.public import admin_account_page
from apps.core.events import EventEnvelope
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.notifications.models import Notification, NotificationReceipt
from apps.notifications.queries import notification_popover
from config.outbox_transport import build_application_event_transport
from tests.fixtures.accounts import bootstrap_test_administrator, create_test_account

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize(
    ("event_type", "expected_title"),
    (
        ("account.registered.v1", "新用户注册"),
        ("account.author_permission_requested.v1", "作者权限申请"),
    ),
)
def test_account_admin_events_deliver_idempotent_notice_with_user_target(
    event_type: str, expected_title: str
) -> None:
    administrator = bootstrap_test_administrator()
    account = create_test_account(
        email=f"{event_type.split('.')[1]}@kaj.test",
        nickname="新用户",
    )
    envelope = EventEnvelope(
        event_id=new_ulid(),
        event_type=event_type,
        schema_version=1,
        occurred_at=timezone.now(),
        actor_id=account.id,
        aggregate_type="account",
        aggregate_id=str(account.id),
        trace_code=new_trace_code(),
        payload={},
    )
    transport = build_application_event_transport()

    transport.publish(envelope)
    transport.publish(envelope)

    assert Notification.objects.count() == 1
    receipt = NotificationReceipt.objects.select_related("notification").get()
    notification = receipt.notification
    assert receipt.recipient_id == administrator.id
    assert notification.template_key == event_type
    assert notification.target_type == "admin_user"
    assert notification.target_id == str(account.id)
    assert notification.payload_safe == {}

    item = notification_popover(recipient_id=administrator.id).items[0]
    assert item.title == expected_title
    assert item.target_url == f"{reverse('admin:users')}?q={account.id}"
    matching = admin_account_page(
        actor_id=administrator.id,
        keyword=str(account.id),
    )
    assert [row.account_id for row in matching.items] == [account.id]
