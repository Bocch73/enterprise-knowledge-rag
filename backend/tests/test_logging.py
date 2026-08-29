"""Structured logging tests."""

import json
import logging

from app.core.logging import JsonFormatter, reset_request_id, set_request_id


def test_json_formatter_includes_context_and_extra_fields() -> None:
    context_token = set_request_id("request-log-1")
    try:
        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="test_event",
            args=(),
            exc_info=None,
        )
        record.component = "logging-test"

        payload = json.loads(JsonFormatter().format(record))

        assert payload["event"] == "test_event"
        assert payload["level"] == "INFO"
        assert payload["request_id"] == "request-log-1"
        assert payload["component"] == "logging-test"
        assert payload["timestamp"].endswith("+00:00")
    finally:
        reset_request_id(context_token)
