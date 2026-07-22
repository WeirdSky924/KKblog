from unittest.mock import Mock

import pytest
from django.test import Client

from apps.operations.services.health import (
    ReadinessChecks,
    ReadinessUnavailable,
    check_readiness,
)


def test_live_does_not_invoke_readiness_checks(monkeypatch) -> None:
    readiness = Mock(side_effect=AssertionError("live must not inspect dependencies"))
    monkeypatch.setattr(
        "apps.operations.presentation.health.check_readiness",
        readiness,
    )

    response = Client().get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}
    assert response.headers["Cache-Control"] == "no-store"
    readiness.assert_not_called()


def test_ready_returns_safe_503_for_any_dependency_failure(monkeypatch) -> None:
    failure = ReadinessUnavailable()
    monkeypatch.setattr(
        "apps.operations.presentation.health.check_readiness",
        Mock(side_effect=failure),
    )

    response = Client().get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response.headers["Cache-Control"] == "no-store"
    assert b"database" not in response.content
    assert b"redis" not in response.content


def test_ready_returns_200_only_after_all_checks_pass(monkeypatch) -> None:
    readiness = Mock(return_value=None)
    monkeypatch.setattr(
        "apps.operations.presentation.health.check_readiness",
        readiness,
    )

    response = Client().get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    readiness.assert_called_once_with()


def test_readiness_stops_on_unavailable_dependency() -> None:
    first = Mock(return_value=None)
    second = Mock(side_effect=RuntimeError("private connection detail"))
    third = Mock(return_value=None)

    with pytest.raises(ReadinessUnavailable) as captured:
        check_readiness(ReadinessChecks(first, second, third))

    assert str(captured.value) == "runtime is not ready"
    first.assert_called_once_with()
    second.assert_called_once_with()
    third.assert_not_called()
