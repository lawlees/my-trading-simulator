
"""Tests for structured performance logging."""

import json
import logging
from unittest.mock import patch

import pytest

from my_trading_simulator.observability.performance import measure


def _performance_events(caplog):
    return [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "my_trading_simulator.performance"
    ]


def test_successful_operation_logs_duration(caplog):
    with caplog.at_level(
        logging.INFO,
        logger="my_trading_simulator.performance",
    ):
        with measure("test_operation"):
            pass

    events = _performance_events(caplog)

    assert len(events) == 1
    assert events[0]["event"] == "performance"
    assert events[0]["operation"] == "test_operation"
    assert events[0]["status"] == "success"
    assert events[0]["duration_ms"] >= 0


def test_failed_operation_logs_error_and_reraises(caplog):
    with caplog.at_level(
        logging.INFO,
        logger="my_trading_simulator.performance",
    ):
        with pytest.raises(ValueError, match="Simulated failure"):
            with measure("failing_operation"):
                raise ValueError("Simulated failure")

    events = _performance_events(caplog)

    assert len(events) == 1
    assert events[0]["status"] == "error"


def test_duration_uses_monotonic_clock(caplog):
    with (
        patch(
            "my_trading_simulator.observability.performance."
            "time.perf_counter",
            side_effect=[10.0, 10.125],
        ),
        caplog.at_level(
            logging.INFO,
            logger="my_trading_simulator.performance",
        ),
    ):
        with measure("timed_operation"):
            pass

    events = _performance_events(caplog)

    assert events[0]["duration_ms"] == 125.0


def test_rejects_invalid_operation_name():
    with pytest.raises(ValueError):
        with measure("access_token=secret"):
            pass


def test_no_exception_details_logged(caplog):
    secret_value = "fake-sensitive-value"

    with caplog.at_level(
        logging.INFO,
        logger="my_trading_simulator.performance",
    ):
        with pytest.raises(RuntimeError):
            with measure("oauth_refresh"):
                raise RuntimeError(secret_value)

    assert secret_value not in caplog.text
    assert "oauth_refresh" in caplog.text


def test_timed_decorator_preserves_result_and_metadata(caplog):
    from my_trading_simulator.observability.performance import timed

    @timed("example_operation")
    def add_values(a, b=1):
        """Test function."""
        return a + b

    with caplog.at_level(logging.INFO, logger="my_trading_simulator.performance"):
        assert add_values(2, b=3) == 5
    assert add_values.__name__ == "add_values"
    assert add_values.__doc__ == "Test function."
    assert _performance_events(caplog)[0]["operation"] == "example_operation"


def test_timed_decorator_reraises_failure(caplog):
    from my_trading_simulator.observability.performance import timed

    @timed("example_failure")
    def fail():
        raise LookupError("fake-secret-string")

    with caplog.at_level(logging.INFO, logger="my_trading_simulator.performance"):
        with pytest.raises(LookupError):
            fail()
    assert _performance_events(caplog)[0]["status"] == "error"
    assert "fake-secret-string" not in caplog.text


def test_timed_decorator_rejects_unsafe_name():
    from my_trading_simulator.observability.performance import timed

    with pytest.raises(ValueError):
        timed("secret=do-not-log")


def test_opt_in_stderr_emits_json_without_payload(monkeypatch, capsys):
    from my_trading_simulator.observability import performance

    monkeypatch.setenv("MY_TRADING_SIMULATOR_PERFORMANCE_LOGGING", "1")
    with measure("api_request"):
        pass

    output = capsys.readouterr().err
    assert '"operation": "api_request"' in output
    assert '"duration_ms"' in output
    # Restore the logger's initial state for other unit tests.
    for handler in list(performance.logger.handlers):
        if getattr(handler, "_mts_performance", False):
            performance.logger.removeHandler(handler)
            handler.close()
    performance.logger.setLevel(logging.NOTSET)
    performance.logger.propagate = True
