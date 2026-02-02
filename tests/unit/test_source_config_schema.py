"""Tests for source config Pydantic schema (US-013)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from asre.config.source_schema import (
    AuthStatusMap,
    EventTypeRules,
    FieldMappings,
    FiltersConfig,
    PairedEvents,
    PairedEventConfig,
    PatientClassRules,
    SourceConfig,
    SourceDefinition,
)


class TestSourceDefinition:
    def test_valid_source_definition(self) -> None:
        sd = SourceDefinition(
            table="raw.adt_events",
            incremental_key="message_ts",
        )
        assert sd.table == "raw.adt_events"
        assert sd.incremental_key == "message_ts"

    def test_table_required(self) -> None:
        with pytest.raises(ValidationError):
            SourceDefinition(incremental_key="ts")  # type: ignore[call-arg]

    def test_incremental_key_required(self) -> None:
        with pytest.raises(ValidationError):
            SourceDefinition(table="raw.adt_events")  # type: ignore[call-arg]


class TestFieldMappings:
    def test_valid_field_mappings(self) -> None:
        fm = FieldMappings(
            patient_key="patient_id",
            event_ts="message_ts",
            source_record_id="msg_control_id",
        )
        assert fm.patient_key == "patient_id"
        assert fm.event_ts == "message_ts"
        assert fm.source_record_id == "msg_control_id"

    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            FieldMappings(patient_key="pid", event_ts="ts")  # type: ignore[call-arg]

    def test_optional_fields_default_none(self) -> None:
        fm = FieldMappings(
            patient_key="pid",
            event_ts="ts",
            source_record_id="rid",
        )
        assert fm.facility_raw is None
        assert fm.patient_class is None
        assert fm.payer_id is None
        assert fm.drg is None
        assert fm.principal_diagnosis is None
        assert fm.admitting_diagnosis is None
        assert fm.diagnosis_codes is None
        assert fm.npi is None
        assert fm.ccn is None


class TestEventTypeRules:
    def test_valid_event_type_rules(self) -> None:
        rules = EventTypeRules(
            source_field="hl7_event",
            mappings={
                "A01": "ADMIT",
                "A03": "DISCHARGE",
                "A02": "TRANSFER_IN",
            },
        )
        assert rules.source_field == "hl7_event"
        assert rules.mappings["A01"] == "ADMIT"

    def test_conditional_mappings(self) -> None:
        rules = EventTypeRules(
            source_field="hl7_event",
            mappings={"A01": "ADMIT"},
            conditional_mappings=[
                {
                    "source_value": "A01",
                    "condition_field": "patient_class",
                    "condition_value": "E",
                    "event_type": "ED_ARRIVAL",
                },
            ],
        )
        assert len(rules.conditional_mappings) == 1
        assert rules.conditional_mappings[0]["event_type"] == "ED_ARRIVAL"

    def test_source_field_required(self) -> None:
        with pytest.raises(ValidationError):
            EventTypeRules(mappings={"A01": "ADMIT"})  # type: ignore[call-arg]

    def test_mappings_required(self) -> None:
        with pytest.raises(ValidationError):
            EventTypeRules(source_field="hl7_event")  # type: ignore[call-arg]

    def test_admit_flag_and_discharge_flag(self) -> None:
        rules = EventTypeRules(
            source_field="hl7_event",
            mappings={"A01": "ADMIT"},
            admit_flag_expression="event_type IN ('ADMIT', 'ED_ARRIVAL', 'OBS_START')",
            discharge_flag_expression="event_type IN ('DISCHARGE', 'ED_DEPARTURE', 'OBS_END')",
        )
        assert rules.admit_flag_expression is not None
        assert rules.discharge_flag_expression is not None


class TestPairedEvents:
    def test_valid_paired_events(self) -> None:
        pe = PairedEvents(
            admit=PairedEventConfig(
                event_ts="admission_date",
                event_type="CLAIM_ADMIT",
            ),
            discharge=PairedEventConfig(
                event_ts="discharge_date",
                event_type="CLAIM_DISCHARGE",
            ),
        )
        assert pe.admit.event_ts == "admission_date"
        assert pe.admit.event_type == "CLAIM_ADMIT"
        assert pe.discharge.event_ts == "discharge_date"
        assert pe.discharge.event_type == "CLAIM_DISCHARGE"

    def test_admit_required(self) -> None:
        with pytest.raises(ValidationError):
            PairedEvents(  # type: ignore[call-arg]
                discharge=PairedEventConfig(
                    event_ts="discharge_date",
                    event_type="CLAIM_DISCHARGE",
                ),
            )

    def test_discharge_required(self) -> None:
        with pytest.raises(ValidationError):
            PairedEvents(  # type: ignore[call-arg]
                admit=PairedEventConfig(
                    event_ts="admission_date",
                    event_type="CLAIM_ADMIT",
                ),
            )


class TestPatientClassRules:
    def test_valid_patient_class_rules(self) -> None:
        rules = PatientClassRules(
            conditions=[
                {"expression": "bill_type_code LIKE '11%'", "patient_class": "inpatient"},
                {"expression": "bill_type_code LIKE '13%'", "patient_class": "outpatient"},
            ],
        )
        assert len(rules.conditions) == 2
        assert rules.conditions[0]["patient_class"] == "inpatient"

    def test_conditions_required(self) -> None:
        with pytest.raises(ValidationError):
            PatientClassRules()  # type: ignore[call-arg]


class TestAuthStatusMap:
    def test_valid_auth_status_map(self) -> None:
        asm = AuthStatusMap(
            source_field="auth_status",
            mappings={
                "A": "approved",
                "D": "denied",
                "P": "pending",
                "M": "modified",
            },
        )
        assert asm.source_field == "auth_status"
        assert asm.mappings["A"] == "approved"
        assert asm.mappings["D"] == "denied"

    def test_source_field_required(self) -> None:
        with pytest.raises(ValidationError):
            AuthStatusMap(mappings={"A": "approved"})  # type: ignore[call-arg]

    def test_mappings_required(self) -> None:
        with pytest.raises(ValidationError):
            AuthStatusMap(source_field="auth_status")  # type: ignore[call-arg]


class TestFiltersConfig:
    def test_valid_filters(self) -> None:
        fc = FiltersConfig(
            exclude="hl7_event IN ('A08', 'A31')",
        )
        assert fc.exclude == "hl7_event IN ('A08', 'A31')"

    def test_exclude_optional(self) -> None:
        fc = FiltersConfig()
        assert fc.exclude is None


class TestSourceConfigADT:
    """Tests for ADT source type."""

    def test_valid_adt_source(self) -> None:
        cfg = SourceConfig(
            name="adt_vendor_x",
            type="adt",
            source=SourceDefinition(
                table="raw.adt_events",
                incremental_key="message_ts",
            ),
            field_mappings=FieldMappings(
                patient_key="patient_id",
                event_ts="message_ts",
                source_record_id="msg_control_id",
                facility_raw="facility_name",
                patient_class="patient_class",
            ),
            event_type_rules=EventTypeRules(
                source_field="hl7_event",
                mappings={
                    "A01": "ADMIT",
                    "A03": "DISCHARGE",
                    "A02": "TRANSFER_IN",
                },
            ),
        )
        assert cfg.name == "adt_vendor_x"
        assert cfg.type == "adt"

    def test_type_must_be_valid(self) -> None:
        with pytest.raises(ValidationError):
            SourceConfig(
                name="bad_source",
                type="invalid_type",
                source=SourceDefinition(
                    table="raw.events",
                    incremental_key="ts",
                ),
                field_mappings=FieldMappings(
                    patient_key="pid",
                    event_ts="ts",
                    source_record_id="rid",
                ),
                event_type_rules=EventTypeRules(
                    source_field="event",
                    mappings={"A01": "ADMIT"},
                ),
            )

    def test_name_required(self) -> None:
        with pytest.raises(ValidationError):
            SourceConfig(  # type: ignore[call-arg]
                type="adt",
                source=SourceDefinition(table="raw.events", incremental_key="ts"),
                field_mappings=FieldMappings(
                    patient_key="pid", event_ts="ts", source_record_id="rid"
                ),
                event_type_rules=EventTypeRules(
                    source_field="e", mappings={"A01": "ADMIT"}
                ),
            )


class TestSourceConfigClaims:
    """Tests for claims source type — must have paired_events."""

    def test_valid_claims_source(self) -> None:
        cfg = SourceConfig(
            name="claims_clearinghouse",
            type="claims",
            source=SourceDefinition(
                table="raw.claims",
                incremental_key="processed_date",
            ),
            field_mappings=FieldMappings(
                patient_key="member_id",
                event_ts="admission_date",
                source_record_id="claim_id",
                facility_raw="facility_name",
                payer_id="payer_code",
                drg="drg_code",
                principal_diagnosis="primary_dx",
                diagnosis_codes="dx_codes",
            ),
            event_type_rules=EventTypeRules(
                source_field="claim_type",
                mappings={"I": "CLAIM_ADMIT"},
            ),
            paired_events=PairedEvents(
                admit=PairedEventConfig(
                    event_ts="admission_date",
                    event_type="CLAIM_ADMIT",
                ),
                discharge=PairedEventConfig(
                    event_ts="discharge_date",
                    event_type="CLAIM_DISCHARGE",
                ),
            ),
        )
        assert cfg.type == "claims"
        assert cfg.paired_events is not None
        assert cfg.paired_events.admit.event_type == "CLAIM_ADMIT"

    def test_claims_requires_paired_events(self) -> None:
        with pytest.raises(ValidationError):
            SourceConfig(
                name="claims_no_paired",
                type="claims",
                source=SourceDefinition(
                    table="raw.claims",
                    incremental_key="ts",
                ),
                field_mappings=FieldMappings(
                    patient_key="pid",
                    event_ts="ts",
                    source_record_id="rid",
                ),
                event_type_rules=EventTypeRules(
                    source_field="ct",
                    mappings={"I": "CLAIM_ADMIT"},
                ),
                # No paired_events — should fail validation
            )


class TestSourceConfigAuth:
    """Tests for auth source type — must have auth_status_map."""

    def test_valid_auth_source(self) -> None:
        cfg = SourceConfig(
            name="auth_portal",
            type="auth",
            source=SourceDefinition(
                table="raw.authorizations",
                incremental_key="updated_at",
            ),
            field_mappings=FieldMappings(
                patient_key="member_id",
                event_ts="auth_date",
                source_record_id="auth_id",
                facility_raw="facility_name",
            ),
            event_type_rules=EventTypeRules(
                source_field="auth_type",
                mappings={"IP": "AUTH_REQUESTED"},
            ),
            auth_status_map=AuthStatusMap(
                source_field="auth_status",
                mappings={
                    "A": "approved",
                    "D": "denied",
                    "P": "pending",
                    "M": "modified",
                },
            ),
        )
        assert cfg.type == "auth"
        assert cfg.auth_status_map is not None
        assert cfg.auth_status_map.mappings["A"] == "approved"

    def test_auth_requires_auth_status_map(self) -> None:
        with pytest.raises(ValidationError):
            SourceConfig(
                name="auth_no_map",
                type="auth",
                source=SourceDefinition(
                    table="raw.auth",
                    incremental_key="ts",
                ),
                field_mappings=FieldMappings(
                    patient_key="pid",
                    event_ts="ts",
                    source_record_id="rid",
                ),
                event_type_rules=EventTypeRules(
                    source_field="at",
                    mappings={"IP": "AUTH_REQUESTED"},
                ),
                # No auth_status_map — should fail validation
            )


class TestSourceConfigOptionalFields:
    """Tests for optional source config fields."""

    def test_filters_optional(self) -> None:
        cfg = SourceConfig(
            name="adt_vendor_x",
            type="adt",
            source=SourceDefinition(table="raw.adt", incremental_key="ts"),
            field_mappings=FieldMappings(
                patient_key="pid", event_ts="ts", source_record_id="rid"
            ),
            event_type_rules=EventTypeRules(
                source_field="e", mappings={"A01": "ADMIT"}
            ),
        )
        assert cfg.filters is None

    def test_filters_populated(self) -> None:
        cfg = SourceConfig(
            name="adt_vendor_x",
            type="adt",
            source=SourceDefinition(table="raw.adt", incremental_key="ts"),
            field_mappings=FieldMappings(
                patient_key="pid", event_ts="ts", source_record_id="rid"
            ),
            event_type_rules=EventTypeRules(
                source_field="e", mappings={"A01": "ADMIT"}
            ),
            filters=FiltersConfig(exclude="hl7_event IN ('A08', 'A31')"),
        )
        assert cfg.filters is not None
        assert cfg.filters.exclude == "hl7_event IN ('A08', 'A31')"

    def test_patient_class_rules_optional(self) -> None:
        cfg = SourceConfig(
            name="adt_vendor_x",
            type="adt",
            source=SourceDefinition(table="raw.adt", incremental_key="ts"),
            field_mappings=FieldMappings(
                patient_key="pid", event_ts="ts", source_record_id="rid"
            ),
            event_type_rules=EventTypeRules(
                source_field="e", mappings={"A01": "ADMIT"}
            ),
        )
        assert cfg.patient_class_rules is None

    def test_paired_events_optional_for_adt(self) -> None:
        cfg = SourceConfig(
            name="adt_vendor_x",
            type="adt",
            source=SourceDefinition(table="raw.adt", incremental_key="ts"),
            field_mappings=FieldMappings(
                patient_key="pid", event_ts="ts", source_record_id="rid"
            ),
            event_type_rules=EventTypeRules(
                source_field="e", mappings={"A01": "ADMIT"}
            ),
        )
        assert cfg.paired_events is None

    def test_auth_status_map_optional_for_adt(self) -> None:
        cfg = SourceConfig(
            name="adt_vendor_x",
            type="adt",
            source=SourceDefinition(table="raw.adt", incremental_key="ts"),
            field_mappings=FieldMappings(
                patient_key="pid", event_ts="ts", source_record_id="rid"
            ),
            event_type_rules=EventTypeRules(
                source_field="e", mappings={"A01": "ADMIT"}
            ),
        )
        assert cfg.auth_status_map is None
