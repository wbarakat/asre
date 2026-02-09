"""CanonicalizeStage - pipeline stage composing all canonicalization logic.

Routes raw records by source type (ADT, claims, auth) to the appropriate
mapping, event type resolution, and enrichment logic. Produces an EventBatch
of CanonicalEvents from raw record dicts.
"""

from __future__ import annotations

import logging
from typing import Any

from asre.canonicalize.auth_status_mapper import AuthStatusMapper
from asre.canonicalize.diagnosis_mapper import DiagnosisCodeMapper
from asre.canonicalize.event_type_resolver import EventTypeResolver
from asre.canonicalize.event_id import generate_event_id
from asre.canonicalize.mapper import FieldMapper
from asre.canonicalize.paired_event_emitter import PairedEventEmitter
from asre.canonicalize.patient_class_resolver import PatientClassResolver
from asre.canonicalize.patient_class_normalizer import normalize_patient_class
from asre.canonicalize.record_validator import process_records_with_tolerance
from asre.config.source_schema import (
    AuthStatusMap,
    EventTypeRules,
    FieldMappings,
    PairedEvents,
    PatientClassRules,
)
from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent
from asre.observability.metrics import StageMetrics
from asre.pipeline.runner import PipelineContext, PipelineStage

logger = logging.getLogger(__name__)


class CanonicalizeStage(PipelineStage):
    """Pipeline stage that converts raw records into CanonicalEvents.

    Routes records to correct mapping logic based on source type:
    - ADT: FieldMapper -> EventTypeResolver
    - Claims: PairedEventEmitter (with PatientClassResolver, DiagnosisCodeMapper)
    - Auth: FieldMapper -> EventTypeResolver -> AuthStatusMapper
    """

    def __init__(self) -> None:
        self.metrics: StageMetrics = StageMetrics("canonicalize", "")

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        """Execute the canonicalize stage.

        Args:
            batch: Input EventBatch (events list will be populated).
            context: Pipeline context with config containing sources and raw_records.

        Returns:
            EventBatch with canonical events populated.
        """
        self.metrics = StageMetrics("canonicalize", context.run_id)

        raw_records: list[dict[str, Any]] = context.config.get("raw_records", [])
        sources = self._normalize_sources(context.config.get("sources", []))

        # Build lookup from source name to config
        source_configs: dict[str, dict[str, Any]] = {
            src["name"]: src for src in sources
        }

        canonical_events: list[CanonicalEvent] = []

        with self.metrics:
            self.metrics.records_in = len(raw_records)

            # Group records by source name
            grouped: dict[str, list[dict[str, Any]]] = {}
            for record in raw_records:
                source_name = record.get("_source_name", "")
                if source_name not in source_configs:
                    logger.warning(
                        "Record from unknown source %s, skipping", source_name
                    )
                    continue
                grouped.setdefault(source_name, []).append(record)

            # Process each source group
            for source_name, records in grouped.items():
                source_cfg = source_configs[source_name]
                events, errors = self._process_source(
                    records, source_cfg, batch.batch_id
                )
                canonical_events.extend(events)
                self.metrics.errors += errors

            self.metrics.records_out = len(canonical_events)

        batch.events = canonical_events
        return batch

    @staticmethod
    def _normalize_sources(sources: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for src in sources:
            if hasattr(src, "model_dump"):
                normalized.append(src.model_dump())
            elif hasattr(src, "dict"):
                normalized.append(src.dict())
            else:
                normalized.append(src)
        return normalized

    def _process_source(
        self,
        records: list[dict[str, Any]],
        source_cfg: dict[str, Any],
        batch_id: str,
    ) -> tuple[list[CanonicalEvent], int]:
        """Process records for a single source.

        Returns:
            Tuple of (canonical_events, error_count).
        """
        source_name: str = source_cfg["name"]
        source_type: str = source_cfg["type"]
        field_mappings = FieldMappings(**source_cfg["field_mappings"])

        # Validate records (error tolerance)
        valid_records, validation_errors = process_records_with_tolerance(
            records, field_mappings
        )
        error_count = len(validation_errors)

        if source_type == "claims":
            events = self._process_claims(
                valid_records, source_cfg, field_mappings, source_name, batch_id
            )
        elif source_type == "auth":
            events = self._process_auth(
                valid_records, source_cfg, field_mappings, source_name, batch_id
            )
        else:
            # ADT or any other type
            events = self._process_adt(
                valid_records, source_cfg, field_mappings, source_name, batch_id
            )

        return events, error_count

    def _process_adt(
        self,
        records: list[dict[str, Any]],
        source_cfg: dict[str, Any],
        field_mappings: FieldMappings,
        source_name: str,
        batch_id: str,
    ) -> list[CanonicalEvent]:
        """Process ADT records: FieldMapper -> EventTypeResolver."""
        mapper = FieldMapper(field_mappings)
        resolver = EventTypeResolver(
            EventTypeRules(**source_cfg["event_type_rules"])
        )

        events: list[CanonicalEvent] = []
        for record in records:
            event = mapper.map_record(record, source_name, batch_id)
            resolver.resolve(event, record)
            event.event_id = generate_event_id(
                source_system=event.source_system,
                source_record_id=event.source_record_id,
                event_type=event.event_type,
            )
            event.patient_class = normalize_patient_class(
                event.patient_class,
                event_type=event.event_type,
            )
            events.append(event)
        return events

    def _process_claims(
        self,
        records: list[dict[str, Any]],
        source_cfg: dict[str, Any],
        field_mappings: FieldMappings,
        source_name: str,
        batch_id: str,
    ) -> list[CanonicalEvent]:
        """Process claims records: PairedEventEmitter + PatientClassResolver + DiagnosisCodeMapper."""
        paired_events = PairedEvents(**source_cfg["paired_events"])
        emitter = PairedEventEmitter(field_mappings, paired_events)
        diagnosis_mapper = DiagnosisCodeMapper(field_mappings)

        patient_class_resolver: PatientClassResolver | None = None
        if source_cfg.get("patient_class_rules"):
            patient_class_resolver = PatientClassResolver(
                PatientClassRules(**source_cfg["patient_class_rules"])
            )

        events: list[CanonicalEvent] = []
        for record in records:
            paired = emitter.emit(record, source_name, batch_id)

            # Resolve patient class from source record
            patient_class: str | None = None
            if patient_class_resolver is not None:
                patient_class = patient_class_resolver.resolve(record)

            # Map diagnosis codes
            diag_codes = diagnosis_mapper.map_diagnosis_codes(record)
            principal_dx = diagnosis_mapper.map_principal_diagnosis(record)
            admitting_dx = diagnosis_mapper.map_admitting_diagnosis(record)
            serialized_codes = DiagnosisCodeMapper.to_serializable(diag_codes)

            for event in paired:
                if patient_class is not None:
                    event.patient_class = normalize_patient_class(
                        patient_class,
                        event_type=event.event_type,
                    )
                else:
                    event.patient_class = normalize_patient_class(
                        event.patient_class,
                        event_type=event.event_type,
                    )
                if principal_dx is not None:
                    event.principal_diagnosis = principal_dx
                if admitting_dx is not None:
                    event.admitting_diagnosis = admitting_dx
                if serialized_codes is not None:
                    event.diagnosis_codes = serialized_codes
                events.append(event)

        return events

    def _process_auth(
        self,
        records: list[dict[str, Any]],
        source_cfg: dict[str, Any],
        field_mappings: FieldMappings,
        source_name: str,
        batch_id: str,
    ) -> list[CanonicalEvent]:
        """Process auth records: FieldMapper -> EventTypeResolver -> AuthStatusMapper."""
        mapper = FieldMapper(field_mappings)
        resolver = EventTypeResolver(
            EventTypeRules(**source_cfg["event_type_rules"])
        )
        auth_mapper = AuthStatusMapper(
            AuthStatusMap(**source_cfg["auth_status_map"])
        )

        events: list[CanonicalEvent] = []
        for record in records:
            event = mapper.map_record(record, source_name, batch_id)
            resolver.resolve(event, record)
            event.event_id = generate_event_id(
                source_system=event.source_system,
                source_record_id=event.source_record_id,
                event_type=event.event_type,
            )
            auth_mapper.apply(event, record)
            event.patient_class = normalize_patient_class(
                event.patient_class,
                event_type=event.event_type,
            )
            events.append(event)
        return events
