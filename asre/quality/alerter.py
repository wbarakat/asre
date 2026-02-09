"""Webhook alerting for quality metric threshold breaches (US-083).

Fires HTTP POST requests to configured webhook URLs when any quality metric
breaches warn or fail thresholds.  Payloads contain ZERO PHI -- only aggregate
metric values, thresholds, and severity levels.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Timeout for each webhook HTTP request (seconds).
_WEBHOOK_TIMEOUT_SECONDS = 5

# Default number of retry attempts on network failure.
_DEFAULT_WEBHOOK_RETRIES = 3

# Base delay for exponential backoff (seconds).
_BACKOFF_BASE_SECONDS = 1.0


class Alerter:
    """Fires webhook alerts when quality metrics breach thresholds.

    Args:
        webhook_urls: List of HTTP(S) endpoint URLs to POST alerts to.
        max_retries: Maximum number of retry attempts per URL (default 3).
        backoff_base: Base delay in seconds for exponential backoff (default 1.0).
    """

    def __init__(
        self,
        webhook_urls: list[str],
        max_retries: int | None = None,
        backoff_base: float | None = None,
    ) -> None:
        self._webhook_urls = webhook_urls
        self._max_retries = max_retries if max_retries is not None else _DEFAULT_WEBHOOK_RETRIES
        self._backoff_base = backoff_base if backoff_base is not None else _BACKOFF_BASE_SECONDS

    def build_payload(
        self,
        run_id: str,
        metrics: dict[str, float],
        statuses: dict[str, str],
        thresholds: dict[str, float],
    ) -> dict[str, Any] | None:
        """Build the webhook alert payload.

        Only metrics with status ``"warn"`` or ``"fail"`` are included in the
        alerts array.  If no metrics are breaching, returns ``None`` (no alert
        needed).

        The payload intentionally contains ZERO PHI -- only aggregate metric
        names, numeric values, threshold values, and severity strings.

        Args:
            run_id: Pipeline run ID.
            metrics: Metric name -> value dict from QualityMetricComputer.
            statuses: Metric name -> status dict from evaluate_thresholds.
            thresholds: Raw threshold config dict.

        Returns:
            Payload dict ready for JSON serialization, or ``None`` if no
            alerts are needed.
        """
        alerts: list[dict[str, Any]] = []
        for metric_name, status in statuses.items():
            if status not in ("warn", "fail"):
                continue
            threshold_key = f"{metric_name}_{status}"
            threshold_value = thresholds.get(threshold_key, 0.0)
            alerts.append(
                {
                    "metric": metric_name,
                    "value": metrics.get(metric_name, 0.0),
                    "threshold": threshold_value,
                    "severity": status,
                }
            )

        if not alerts:
            return None

        return {
            "run_id": run_id,
            "run_ts": datetime.now(tz=timezone.utc).isoformat(),
            "alerts": alerts,
        }

    def fire(
        self,
        run_id: str,
        metrics: dict[str, float],
        statuses: dict[str, str],
        thresholds: dict[str, float],
    ) -> bool:
        """Build payload and POST to all configured webhook URLs.

        Webhook failures (network errors, non-2xx responses) are logged but
        do **not** raise exceptions -- alerting must never block the pipeline.

        Args:
            run_id: Pipeline run ID.
            metrics: Metric name -> value dict.
            statuses: Metric name -> status dict.
            thresholds: Raw threshold config dict.

        Returns:
            ``True`` if at least one webhook received the alert successfully,
            ``False`` if no webhooks were configured, no alerts needed, or all
            deliveries failed.
        """
        if not self._webhook_urls:
            logger.debug("No webhook URLs configured; skipping alerting.")
            return False

        payload = self.build_payload(run_id, metrics, statuses, thresholds)
        if payload is None:
            logger.info("All metrics passing; no alerts to fire.")
            return False

        body = json.dumps(payload).encode("utf-8")
        any_success = False

        for url in self._webhook_urls:
            success = self._post(url, body)
            if success:
                any_success = True

        return any_success

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _post(self, url: str, body: bytes) -> bool:
        """POST *body* to *url* with retries and exponential backoff.

        Returns ``True`` on a 2xx response, ``False`` otherwise.
        """
        total_attempts = self._max_retries + 1
        for attempt in range(total_attempts):
            try:
                req = Request(
                    url,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(req, timeout=_WEBHOOK_TIMEOUT_SECONDS) as resp:
                    if 200 <= resp.status < 300:
                        logger.info(
                            "Webhook alert delivered to %s (status %d)",
                            url,
                            resp.status,
                        )
                        return True
                    logger.warning(
                        "Webhook %s returned status %d (attempt %d/%d)",
                        url,
                        resp.status,
                        attempt + 1,
                        total_attempts,
                    )
            except (URLError, OSError, TimeoutError) as exc:
                logger.warning(
                    "Webhook delivery to %s failed (attempt %d/%d): %s",
                    url,
                    attempt + 1,
                    total_attempts,
                    exc,
                )

            # Exponential backoff before next retry (skip after last attempt)
            if attempt < self._max_retries:
                delay = self._backoff_base * (2 ** attempt)
                time.sleep(delay)

        logger.error("All webhook delivery attempts to %s exhausted.", url)
        return False
