"""Pipeline-level error tolerance for ASRE (US-077).

Computes failed_event_rate across pipeline stages and halts if the rate
exceeds a configurable threshold.
"""

from __future__ import annotations


class FailedEventRateExceededError(Exception):
    """Raised when the failed event rate exceeds the configured threshold."""

    def __init__(
        self, rate: float, threshold: float, failed: int, total: int
    ) -> None:
        self.rate = rate
        self.threshold = threshold
        self.failed = failed
        self.total = total
        super().__init__(
            f"Failed event rate {rate:.2%} exceeds threshold {threshold:.2%} "
            f"({failed}/{total} events failed)"
        )


class ErrorToleranceChecker:
    """Checks whether the failed event rate is within acceptable bounds.

    Args:
        fail_threshold: Maximum acceptable failed_event_rate (0.0-1.0).
            If the rate meets or exceeds this value, the pipeline halts.
    """

    def __init__(self, fail_threshold: float) -> None:
        self.fail_threshold = fail_threshold

    def compute_rate(self, failed: int, total: int) -> float:
        """Compute the failed event rate.

        Returns 0.0 if total is zero (no events processed).
        """
        if total == 0:
            return 0.0
        return failed / total

    def check(self, failed: int, total: int) -> None:
        """Check the failed event rate against the threshold.

        Raises:
            FailedEventRateExceededError: If rate >= fail_threshold.
        """
        rate = self.compute_rate(failed, total)
        if rate >= self.fail_threshold:
            raise FailedEventRateExceededError(
                rate=rate,
                threshold=self.fail_threshold,
                failed=failed,
                total=total,
            )
