import logging
from unittest.mock import Mock

import pytest

from apps.operations.services.performance import (
    RICH_TEXT_RENDER_BUDGET_MS,
    record_rich_text_render_metric,
)


def test_rich_text_render_metric_logs_only_bounded_safe_dimensions(monkeypatch) -> None:
    captured = Mock()
    monkeypatch.setattr("apps.operations.services.performance.logger.log", captured)

    record_rich_text_render_metric(
        content_format="TIPTAP_JSON",
        mode="strict",
        schema_version=2,
        source_bytes=2048,
        node_count=41,
        max_depth=4,
        table_cells=6,
        duration_ms=12.3456,
        outcome="success",
        error_code="-",
    )

    assert RICH_TEXT_RENDER_BUDGET_MS == 250.0
    message = captured.call_args.args[1] % captured.call_args.args[2:]
    assert message == (
        "Rich text render format=TIPTAP_JSON mode=strict schema=2 "
        "source_bytes=2048 nodes=41 depth=4 table_cells=6 "
        "duration_ms=12.346 budget_ms=250.000 outcome=success code=-"
    )
    assert captured.call_args.kwargs == {}
    assert captured.call_args.args[0] == logging.INFO

    captured.reset_mock()
    record_rich_text_render_metric(
        content_format="MARKDOWN",
        mode="reader",
        schema_version=None,
        source_bytes=4096,
        node_count=0,
        max_depth=0,
        table_cells=0,
        duration_ms=250.001,
        outcome="success",
        error_code="-",
    )
    assert captured.call_args.args[0] == logging.WARNING


@pytest.mark.parametrize(
    "field,value",
    [
        ("content_format", "<script>private</script>"),
        ("mode", "private-mode"),
        ("error_code", "private content"),
        ("node_count", -1),
        ("duration_ms", float("inf")),
    ],
)
def test_rich_text_render_metric_rejects_unbounded_dimensions(field, value) -> None:
    values = {
        "content_format": "MARKDOWN",
        "mode": "reader",
        "schema_version": None,
        "source_bytes": 100,
        "node_count": 0,
        "max_depth": 0,
        "table_cells": 0,
        "duration_ms": 1.0,
        "outcome": "rejected",
        "error_code": "content.body_invalid.v1",
    }
    values[field] = value
    with pytest.raises((TypeError, ValueError)):
        record_rich_text_render_metric(**values)
