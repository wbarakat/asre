"""Pipeline stage interface and context for ASRE pipeline composition."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from asre.models.batch import EventBatch


@dataclass
class PipelineContext:
    """Context passed to each pipeline stage during execution.

    Holds run-level state: run_id, config, mode, and optional metrics collector.
    """

    run_id: str
    config: dict[str, Any]
    mode: str
    metrics_collector: Any = field(default=None)


class PipelineStage(ABC):
    """Abstract base class for all ASRE pipeline stages.

    Each stage processes an EventBatch and returns a (possibly modified) EventBatch.
    """

    @abstractmethod
    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        """Execute this pipeline stage.

        Args:
            batch: The current event batch to process.
            context: Pipeline-level context (run_id, config, mode, metrics).

        Returns:
            The processed EventBatch.
        """
