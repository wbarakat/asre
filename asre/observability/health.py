"""Lightweight HTTP health check endpoint for container orchestration.

Uses only Python stdlib (http.server) to minimize overhead.
Exposes /health returning JSON with pipeline status.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any


class PipelineHealthState:
    """Thread-safe pipeline health state tracker.

    Tracks whether the pipeline is healthy or in a failed state.
    Used by the health check HTTP endpoint to determine response code.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status: str = "ok"
        self._error: str | None = None

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    def is_healthy(self) -> bool:
        with self._lock:
            return self._status == "ok"

    def mark_failed(self, error: str) -> None:
        with self._lock:
            self._status = "failed"
            self._error = error

    def mark_ok(self) -> None:
        with self._lock:
            self._status = "ok"
            self._error = None

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            d: dict[str, Any] = {"status": self._status}
            if self._error is not None:
                d["error"] = self._error
            return d


class _HealthHandler(BaseHTTPRequestHandler):
    """HTTP request handler for /health endpoint."""

    server: HealthCheckServer

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            state = self.server.health_state
            body = json.dumps(state.to_dict()).encode("utf-8")
            status_code = 200 if state.is_healthy() else 503
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default stderr logging to avoid noise."""
        pass


class HealthCheckServer(HTTPServer):
    """Lightweight HTTP server for health checks.

    Args:
        port: TCP port to listen on. Use 0 for a random available port.
        state: Shared PipelineHealthState instance.
        bind_address: Address to bind to (default "0.0.0.0").
    """

    def __init__(
        self,
        port: int = 8080,
        state: PipelineHealthState | None = None,
        bind_address: str = "0.0.0.0",
    ) -> None:
        self.health_state = state or PipelineHealthState()
        super().__init__((bind_address, port), _HealthHandler)

    def get_port(self) -> int:
        """Return the port the server is listening on."""
        return self.server_address[1]
