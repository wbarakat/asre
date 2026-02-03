"""Tests for health check HTTP endpoint."""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from asre.observability.health import HealthCheckServer, PipelineHealthState


class TestPipelineHealthState:
    """Tests for pipeline health state tracking."""

    def test_initial_state_is_ok(self) -> None:
        state = PipelineHealthState()
        assert state.status == "ok"
        assert state.is_healthy()

    def test_mark_failed_sets_failed_status(self) -> None:
        state = PipelineHealthState()
        state.mark_failed("Stage 'ingest' failed: connection timeout")
        assert state.status == "failed"
        assert not state.is_healthy()
        assert state.error == "Stage 'ingest' failed: connection timeout"

    def test_mark_ok_resets_to_healthy(self) -> None:
        state = PipelineHealthState()
        state.mark_failed("error")
        state.mark_ok()
        assert state.status == "ok"
        assert state.is_healthy()
        assert state.error is None

    def test_to_dict_healthy(self) -> None:
        state = PipelineHealthState()
        d = state.to_dict()
        assert d["status"] == "ok"
        assert "error" not in d or d.get("error") is None

    def test_to_dict_failed(self) -> None:
        state = PipelineHealthState()
        state.mark_failed("boom")
        d = state.to_dict()
        assert d["status"] == "failed"
        assert d["error"] == "boom"


class TestHealthCheckServer:
    """Tests for the health check HTTP server."""

    def test_health_endpoint_returns_200_when_healthy(self) -> None:
        state = PipelineHealthState()
        server = HealthCheckServer(port=0, state=state)  # port=0 for random
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_port
            url = f"http://127.0.0.1:{port}/health"
            with urllib.request.urlopen(url, timeout=5) as resp:
                assert resp.status == 200
                body = json.loads(resp.read().decode())
                assert body["status"] == "ok"
        finally:
            server.shutdown()

    def test_health_endpoint_returns_503_when_failed(self) -> None:
        state = PipelineHealthState()
        state.mark_failed("pipeline crashed")
        server = HealthCheckServer(port=0, state=state)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_port
            url = f"http://127.0.0.1:{port}/health"
            try:
                urllib.request.urlopen(url, timeout=5)
                pytest.fail("Expected HTTPError with 503")
            except urllib.error.HTTPError as exc:
                assert exc.code == 503
                body = json.loads(exc.read().decode())
                assert body["status"] == "failed"
                assert body["error"] == "pipeline crashed"
        finally:
            server.shutdown()

    def test_non_health_path_returns_404(self) -> None:
        state = PipelineHealthState()
        server = HealthCheckServer(port=0, state=state)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_port
            url = f"http://127.0.0.1:{port}/other"
            try:
                urllib.request.urlopen(url, timeout=5)
                pytest.fail("Expected HTTPError with 404")
            except urllib.error.HTTPError as exc:
                assert exc.code == 404
        finally:
            server.shutdown()

    def test_server_uses_configured_port(self) -> None:
        """Server binds to the specified port (port=0 picks random available)."""
        state = PipelineHealthState()
        server = HealthCheckServer(port=0, state=state)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            assert server.server_port > 0
        finally:
            server.shutdown()

    def test_health_response_content_type_is_json(self) -> None:
        state = PipelineHealthState()
        server = HealthCheckServer(port=0, state=state)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_port
            url = f"http://127.0.0.1:{port}/health"
            with urllib.request.urlopen(url, timeout=5) as resp:
                assert "application/json" in resp.headers.get("Content-Type", "")
        finally:
            server.shutdown()

    def test_state_change_reflected_in_response(self) -> None:
        """State changes between requests are reflected."""
        state = PipelineHealthState()
        server = HealthCheckServer(port=0, state=state)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_port
            url = f"http://127.0.0.1:{port}/health"

            # First request: healthy
            with urllib.request.urlopen(url, timeout=5) as resp:
                assert resp.status == 200

            # Mark failed
            state.mark_failed("oops")

            # Second request: unhealthy
            try:
                urllib.request.urlopen(url, timeout=5)
                pytest.fail("Expected 503")
            except urllib.error.HTTPError as exc:
                assert exc.code == 503
        finally:
            server.shutdown()
