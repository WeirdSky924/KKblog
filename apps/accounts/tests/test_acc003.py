import json

import pytest

from apps.accounts.models import SecurityEvent
from apps.accounts.services.verification import (
    VerificationError,
    VerificationPurpose,
    VerificationStore,
    request_verification_code,
    verify_code,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def store(isolated_redis):
    client, prefix = isolated_redis
    return VerificationStore(client=client, namespace=prefix.rstrip(":"))


def test_mailpit_delivery_and_digest_only_storage(store, mailpit) -> None:
    request_verification_code(
        purpose=VerificationPurpose.REGISTRATION,
        email="new-user@kaj.test",
        client_ip="203.0.113.5",
        trace_code="KJ-VERIFY-SEND",
        store=store,
        code_generator=lambda: "123456",
    )
    messages = mailpit.messages()
    assert len(messages) == 1
    assert messages[0]["To"][0]["Address"] == "new-user@kaj.test"
    keys = list(store.client.scan_iter(match=f"{store.namespace}:*"))
    stored = b" ".join(
        str(store.client.hgetall(key)).encode() for key in keys if b":challenge:" in key
    )
    assert b"123456" not in stored
    values = store.client.hgetall(
        store.challenge_key(
            purpose=VerificationPurpose.REGISTRATION,
            email="new-user@kaj.test",
        )
    )
    event = SecurityEvent.objects.get()
    assert set(item.decode() for item in values) == {"attempts", "binding", "digest"}
    assert event.event_type == "VERIFICATION_CODE_SENT"
    assert "123456" not in json.dumps(event.safe_summary)


def test_purpose_isolation_and_success_consumes_challenge(store, mailpit) -> None:
    request_verification_code(
        purpose=VerificationPurpose.LOGIN,
        email="person@kaj.test",
        client_ip="203.0.113.6",
        trace_code="KJ-VERIFY-LOGIN",
        store=store,
        code_generator=lambda: "234567",
    )
    with pytest.raises(VerificationError):
        verify_code(
            purpose=VerificationPurpose.PASSWORD_RESET,
            email="person@kaj.test",
            code="234567",
            store=store,
        )
    verify_code(
        purpose=VerificationPurpose.LOGIN,
        email="person@kaj.test",
        code="234567",
        store=store,
    )
    with pytest.raises(VerificationError):
        verify_code(
            purpose=VerificationPurpose.LOGIN,
            email="person@kaj.test",
            code="234567",
            store=store,
        )


def test_resend_interval_new_code_override_and_fifth_failure(store, mailpit) -> None:
    kwargs = {
        "purpose": VerificationPurpose.NEW_EMAIL,
        "email": "change@kaj.test",
        "client_ip": "203.0.113.7",
        "trace_code": "KJ-VERIFY-CHANGE",
        "store": store,
    }
    request_verification_code(**kwargs, code_generator=lambda: "345678")
    with pytest.raises(VerificationError):
        request_verification_code(**kwargs, code_generator=lambda: "456789")
    store.clear_send_restriction(email="change@kaj.test")
    request_verification_code(**kwargs, code_generator=lambda: "456789")
    with pytest.raises(VerificationError):
        verify_code(
            purpose=VerificationPurpose.NEW_EMAIL,
            email="change@kaj.test",
            code="345678",
            store=store,
        )
    for _ in range(4):
        with pytest.raises(VerificationError):
            verify_code(
                purpose=VerificationPurpose.NEW_EMAIL,
                email="change@kaj.test",
                code="000000",
                store=store,
            )
    with pytest.raises(VerificationError):
        verify_code(
            purpose=VerificationPurpose.NEW_EMAIL,
            email="change@kaj.test",
            code="456789",
            store=store,
        )


def test_redis_loss_invalidates_challenge(store, mailpit) -> None:
    request_verification_code(
        purpose=VerificationPurpose.REGISTRATION,
        email="lost@kaj.test",
        client_ip="203.0.113.8",
        trace_code="KJ-VERIFY-LOST",
        store=store,
        code_generator=lambda: "567890",
    )
    store.client.delete(*list(store.client.scan_iter(match=f"{store.namespace}:*")))
    with pytest.raises(VerificationError):
        verify_code(
            purpose=VerificationPurpose.REGISTRATION,
            email="lost@kaj.test",
            code="567890",
            store=store,
        )
