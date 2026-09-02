import json

import pytest
from django.test import RequestFactory

from apps.administration.views.opportunities import opportunities
from apps.notifications.models import NotificationReceipt
from apps.notifications.public import (
    NotificationTemplateSchema,
    deliver_notification,
    mark_target_notifications_read,
    register_notification_template,
    unread_target_notification_count,
)
from tests.fixtures.accounts import bootstrap_test_administrator

pytestmark = pytest.mark.django_db

_RUN_TEMPLATE = "test.opportunity-run-read.v1"
_OTHER_TEMPLATE = "test.other-target-read.v1"


def _register_test_templates() -> None:
    register_notification_template(
        NotificationTemplateSchema(
            key=_RUN_TEMPLATE,
            target_type="opportunity_check_run",
            allowed_payload_fields=frozenset(),
        )
    )
    register_notification_template(
        NotificationTemplateSchema(
            key=_OTHER_TEMPLATE,
            target_type="other_target",
            allowed_payload_fields=frozenset(),
        )
    )


def _deliver(template_key: str, *, recipient_id, target_id: str) -> None:
    deliver_notification(
        template_key=template_key,
        recipient_ids=(recipient_id,),
        target_id=target_id,
        payload={},
    )


def test_target_read_service_only_marks_the_selected_notification_kind() -> None:
    administrator = bootstrap_test_administrator()
    _register_test_templates()
    _deliver(_RUN_TEMPLATE, recipient_id=administrator.id, target_id="run-1")
    _deliver(_RUN_TEMPLATE, recipient_id=administrator.id, target_id="run-2")
    _deliver(_OTHER_TEMPLATE, recipient_id=administrator.id, target_id="other-1")

    assert (
        unread_target_notification_count(
            recipient_id=administrator.id,
            target_type="opportunity_check_run",
        )
        == 2
    )
    assert (
        mark_target_notifications_read(
            recipient_id=administrator.id,
            target_type="opportunity_check_run",
        )
        == 2
    )
    assert (
        unread_target_notification_count(
            recipient_id=administrator.id,
            target_type="opportunity_check_run",
        )
        == 0
    )
    assert NotificationReceipt.objects.filter(read_at__isnull=True).count() == 1


def test_task_history_read_action_updates_shared_notification_state() -> None:
    administrator = bootstrap_test_administrator()
    _register_test_templates()
    _deliver(_RUN_TEMPLATE, recipient_id=administrator.id, target_id="run-1")
    request = RequestFactory().post(
        "/admin/opportunities/?tab=runs",
        {"action": "mark_runs_read"},
        HTTP_HX_REQUEST="true",
    )
    request.account_id = administrator.id
    request.client_ip = "127.0.0.1"
    request.trace_code = "KJ-OPP-RUN-READ"

    response = opportunities(request)

    assert response.status_code == 204
    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger["kaj:administration-attention-read"] == {
        "key": "opportunities-runs",
        "count": 0,
        "notificationUnreadCount": 0,
    }
    assert NotificationReceipt.objects.get().read_at is not None
