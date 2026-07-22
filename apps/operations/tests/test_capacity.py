from datetime import UTC, datetime

import pytest
from django.http import JsonResponse
from django.test import Client, override_settings
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from apps.core.errors import DomainError, ErrorCode
from apps.operations.services.capacity import (
    CapacityGate,
    CapacityOperation,
    CapacityPolicy,
    CapacitySample,
    CapacityState,
    capacity_health_snapshot,
)

OBSERVED_AT = datetime(2026, 7, 22, 5, 0, tzinfo=UTC)
TOTAL_BYTES = 10_000
_probe_gate = None
_probe_calls = []


def _sample(free_bytes: int) -> CapacitySample:
    return CapacitySample(
        total_bytes=TOTAL_BYTES,
        free_bytes=free_bytes,
        observed_at=OBSERVED_AT,
    )


@csrf_exempt
def image_create_probe(request):
    assert request.method == "POST"
    assert _probe_gate is not None
    _probe_gate.require(CapacityOperation.IMAGE_CREATE)
    _probe_calls.append("image")
    return JsonResponse({"created": True}, status=201)


@csrf_exempt
def text_create_probe(request):
    assert request.method == "POST"
    assert _probe_gate is not None
    _probe_gate.require(CapacityOperation.TEXT_CREATE)
    _probe_calls.append("text")
    return JsonResponse({"created": True}, status=201)


urlpatterns = [
    path("capacity/image", image_create_probe),
    path("capacity/text", text_create_probe),
]


@pytest.mark.parametrize(
    ("free_bytes", "state", "text_allowed", "image_allowed"),
    [
        (10_000, CapacityState.NORMAL, True, True),
        (1_000, CapacityState.NORMAL, True, True),
        (999, CapacityState.WARN, True, True),
        (500, CapacityState.WARN, True, True),
        (499, CapacityState.NO_IMAGE, True, False),
        (200, CapacityState.NO_IMAGE, True, False),
        (199, CapacityState.READ_ONLY, False, False),
        (0, CapacityState.READ_ONLY, False, False),
    ],
)
def test_capacity_policy_exact_boundaries(
    free_bytes: int,
    state: CapacityState,
    text_allowed: bool,
    image_allowed: bool,
) -> None:
    decision = CapacityPolicy().evaluate(_sample(free_bytes))

    assert decision.state == state
    assert decision.text_creation_allowed is text_allowed
    assert decision.image_creation_allowed is image_allowed
    assert decision.diagnostic_write_allowed is True
    assert decision.existing_content_read_allowed is True


def test_capacity_sample_rejects_invalid_or_naive_values() -> None:
    with pytest.raises(ValueError, match="total_bytes"):
        CapacitySample(total_bytes=0, free_bytes=0, observed_at=OBSERVED_AT)
    with pytest.raises(ValueError, match="free_bytes"):
        CapacitySample(total_bytes=100, free_bytes=101, observed_at=OBSERVED_AT)
    with pytest.raises(ValueError, match="observed_at"):
        CapacitySample(
            total_bytes=100,
            free_bytes=50,
            observed_at=datetime(2026, 7, 22, 5, 0),
        )


def test_gate_rereads_trusted_source_and_recovers_automatically() -> None:
    current = [_sample(199)]
    source_calls = []

    def source() -> CapacitySample:
        source_calls.append(current[0])
        return current[0]

    gate = CapacityGate(source)
    with pytest.raises(DomainError) as blocked:
        gate.require(CapacityOperation.TEXT_CREATE)
    assert blocked.value.code == ErrorCode.CONTENT_CREATION_BLOCKED

    current[0] = _sample(200)
    recovered = gate.require(CapacityOperation.TEXT_CREATE)
    assert recovered.state == CapacityState.NO_IMAGE
    assert source_calls == [_sample(199), _sample(200)]


def test_read_only_keeps_diagnostic_write_and_existing_reads_available() -> None:
    gate = CapacityGate(lambda: _sample(0))

    decision = gate.require(CapacityOperation.DIAGNOSTIC_WRITE)
    health = capacity_health_snapshot(gate)

    assert decision.state == CapacityState.READ_ONLY
    assert health.state == CapacityState.READ_ONLY
    assert health.existing_content_read_allowed is True
    assert health.diagnostic_write_allowed is True


@override_settings(ROOT_URLCONF=__name__)
def test_direct_posts_are_blocked_before_commands_and_return_safe_messages() -> None:
    global _probe_gate
    _probe_calls.clear()
    client = Client()

    _probe_gate = CapacityGate(lambda: _sample(499))
    image = client.post("/capacity/image")
    text = client.post("/capacity/text")

    assert image.status_code == 503
    assert "暂时不支持上传图片" in image.content.decode("utf-8")
    assert image.headers["Cache-Control"] == "no-store"
    assert text.status_code == 201
    assert _probe_calls == ["text"]

    _probe_gate = CapacityGate(lambda: _sample(199))
    image = client.post("/capacity/image")
    text = client.post("/capacity/text")

    assert image.status_code == 503
    assert text.status_code == 503
    assert "暂时无法创建新内容" in text.content.decode("utf-8")
    assert _probe_calls == ["text"]


def test_multiple_consumers_read_the_same_policy_result() -> None:
    sample = _sample(350)
    content_gate = CapacityGate(lambda: sample)
    media_gate = CapacityGate(lambda: sample)
    health_gate = CapacityGate(lambda: sample)

    content = content_gate.require(CapacityOperation.TEXT_CREATE)
    with pytest.raises(DomainError) as media:
        media_gate.require(CapacityOperation.IMAGE_CREATE)
    health = capacity_health_snapshot(health_gate)

    assert content.state == health.state == CapacityState.NO_IMAGE
    assert media.value.code == ErrorCode.IMAGE_CREATION_BLOCKED
    assert health.free_bytes == sample.free_bytes
    assert health.total_bytes == sample.total_bytes
