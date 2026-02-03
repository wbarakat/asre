"""Tests for asre.quality.alerter (US-083)."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from asre.quality.alerter import Alerter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_metrics() -> dict[str, float]:
    return {
        "duplicate_rate": 0.18,
        "missing_discharge_rate": 0.12,
        "low_confidence_rate": 0.05,
        "avg_confidence_score": 0.75,
    }


def _sample_statuses() -> dict[str, str]:
    return {
        "duplicate_rate": "fail",
        "missing_discharge_rate": "warn",
        "low_confidence_rate": "pass",
        "avg_confidence_score": "pass",
    }


def _sample_thresholds() -> dict[str, float]:
    return {
        "duplicate_rate_warn": 0.05,
        "duplicate_rate_fail": 0.15,
        "missing_discharge_rate_warn": 0.10,
        "missing_discharge_rate_fail": 0.25,
    }


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------

class TestAlerterImport:
    def test_alerter_importable(self) -> None:
        from asre.quality.alerter import Alerter  # noqa: F811
        assert Alerter is not None


# ---------------------------------------------------------------------------
# Payload construction
# ---------------------------------------------------------------------------

class TestBuildPayload:
    def test_returns_none_when_all_pass(self) -> None:
        alerter = Alerter(webhook_urls=["http://example.com/hook"])
        statuses = {"dup": "pass", "miss": "pass"}
        result = alerter.build_payload("run_1", {}, statuses, {})
        assert result is None

    def test_includes_only_warn_and_fail(self) -> None:
        alerter = Alerter(webhook_urls=[])
        payload = alerter.build_payload(
            "run_1", _sample_metrics(), _sample_statuses(), _sample_thresholds()
        )
        assert payload is not None
        alert_metrics = {a["metric"] for a in payload["alerts"]}
        assert alert_metrics == {"duplicate_rate", "missing_discharge_rate"}

    def test_payload_structure(self) -> None:
        alerter = Alerter(webhook_urls=[])
        payload = alerter.build_payload(
            "run_1", _sample_metrics(), _sample_statuses(), _sample_thresholds()
        )
        assert payload is not None
        assert "run_id" in payload
        assert "run_ts" in payload
        assert "alerts" in payload
        assert payload["run_id"] == "run_1"

    def test_alert_entry_fields(self) -> None:
        alerter = Alerter(webhook_urls=[])
        payload = alerter.build_payload(
            "run_1", _sample_metrics(), _sample_statuses(), _sample_thresholds()
        )
        assert payload is not None
        for alert in payload["alerts"]:
            assert "metric" in alert
            assert "value" in alert
            assert "threshold" in alert
            assert "severity" in alert
            assert alert["severity"] in ("warn", "fail")

    def test_fail_alert_uses_fail_threshold(self) -> None:
        alerter = Alerter(webhook_urls=[])
        payload = alerter.build_payload(
            "run_1", _sample_metrics(), _sample_statuses(), _sample_thresholds()
        )
        assert payload is not None
        dup_alert = next(a for a in payload["alerts"] if a["metric"] == "duplicate_rate")
        assert dup_alert["threshold"] == 0.15
        assert dup_alert["severity"] == "fail"
        assert dup_alert["value"] == 0.18

    def test_warn_alert_uses_warn_threshold(self) -> None:
        alerter = Alerter(webhook_urls=[])
        payload = alerter.build_payload(
            "run_1", _sample_metrics(), _sample_statuses(), _sample_thresholds()
        )
        assert payload is not None
        miss_alert = next(
            a for a in payload["alerts"] if a["metric"] == "missing_discharge_rate"
        )
        assert miss_alert["threshold"] == 0.10
        assert miss_alert["severity"] == "warn"
        assert miss_alert["value"] == 0.12

    def test_no_phi_in_payload(self) -> None:
        """Verify payload contains ZERO PHI -- only aggregate metrics."""
        alerter = Alerter(webhook_urls=[])
        payload = alerter.build_payload(
            "run_1", _sample_metrics(), _sample_statuses(), _sample_thresholds()
        )
        assert payload is not None
        payload_str = json.dumps(payload)

        # PHI-related terms that must NOT appear
        phi_terms = [
            "patient",
            "mrn",
            "ssn",
            "name",
            "dob",
            "address",
            "phone",
            "email",
            "facility_name",
            "diagnosis",
            "drg",
            "payer",
        ]
        payload_lower = payload_str.lower()
        for term in phi_terms:
            assert term not in payload_lower, (
                f"PHI-related term '{term}' found in webhook payload"
            )

    def test_payload_is_json_serializable(self) -> None:
        alerter = Alerter(webhook_urls=[])
        payload = alerter.build_payload(
            "run_1", _sample_metrics(), _sample_statuses(), _sample_thresholds()
        )
        assert payload is not None
        # Should not raise
        serialized = json.dumps(payload)
        roundtripped = json.loads(serialized)
        assert roundtripped["run_id"] == "run_1"


# ---------------------------------------------------------------------------
# Webhook firing
# ---------------------------------------------------------------------------

class TestFire:
    def test_returns_false_when_no_urls(self) -> None:
        alerter = Alerter(webhook_urls=[])
        result = alerter.fire("run_1", _sample_metrics(), _sample_statuses(), _sample_thresholds())
        assert result is False

    def test_returns_false_when_all_pass(self) -> None:
        alerter = Alerter(webhook_urls=["http://example.com/hook"])
        statuses = {k: "pass" for k in _sample_metrics()}
        result = alerter.fire("run_1", _sample_metrics(), statuses, _sample_thresholds())
        assert result is False

    @patch("asre.quality.alerter.urlopen")
    def test_posts_to_single_webhook(self, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        alerter = Alerter(webhook_urls=["http://example.com/hook"])
        result = alerter.fire("run_1", _sample_metrics(), _sample_statuses(), _sample_thresholds())
        assert result is True
        mock_urlopen.assert_called_once()

        # Verify the request body is valid JSON
        call_args = mock_urlopen.call_args
        request_obj = call_args[0][0]
        body = json.loads(request_obj.data.decode("utf-8"))
        assert body["run_id"] == "run_1"
        assert len(body["alerts"]) == 2

    @patch("asre.quality.alerter.urlopen")
    def test_posts_to_multiple_webhooks(self, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        alerter = Alerter(
            webhook_urls=["http://example.com/hook1", "http://example.com/hook2"]
        )
        result = alerter.fire("run_1", _sample_metrics(), _sample_statuses(), _sample_thresholds())
        assert result is True
        assert mock_urlopen.call_count == 2

    @patch("asre.quality.alerter.urlopen")
    def test_network_failure_does_not_raise(self, mock_urlopen: MagicMock) -> None:
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")

        alerter = Alerter(webhook_urls=["http://example.com/hook"])
        # Must not raise
        result = alerter.fire("run_1", _sample_metrics(), _sample_statuses(), _sample_thresholds())
        assert result is False

    @patch("asre.quality.alerter.urlopen")
    def test_retries_on_failure(self, mock_urlopen: MagicMock) -> None:
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")

        alerter = Alerter(webhook_urls=["http://example.com/hook"])
        alerter.fire("run_1", _sample_metrics(), _sample_statuses(), _sample_thresholds())
        # 1 initial attempt + 1 retry = 2
        assert mock_urlopen.call_count == 2

    @patch("asre.quality.alerter.urlopen")
    def test_partial_success_returns_true(self, mock_urlopen: MagicMock) -> None:
        """If one webhook succeeds and another fails, returns True."""
        from urllib.error import URLError

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        # First URL succeeds, second fails
        mock_urlopen.side_effect = [mock_resp, URLError("fail"), URLError("fail")]

        alerter = Alerter(
            webhook_urls=["http://example.com/ok", "http://example.com/bad"]
        )
        result = alerter.fire("run_1", _sample_metrics(), _sample_statuses(), _sample_thresholds())
        assert result is True

    @patch("asre.quality.alerter.urlopen")
    def test_content_type_header(self, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        alerter = Alerter(webhook_urls=["http://example.com/hook"])
        alerter.fire("run_1", _sample_metrics(), _sample_statuses(), _sample_thresholds())

        request_obj = mock_urlopen.call_args[0][0]
        assert request_obj.get_header("Content-type") == "application/json"
