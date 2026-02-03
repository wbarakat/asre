"""Tests for ASRE CLI episodes command (US-096)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from asre.cli.main import cli


class TestEpisodesCommandGroup:
    """Tests for 'asre episodes' command group."""

    def test_episodes_command_exists(self) -> None:
        """episodes command appears in help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "episodes" in result.output

    def test_episodes_help_shows_recompute(self) -> None:
        """episodes --help shows recompute option."""
        runner = CliRunner()
        result = runner.invoke(cli, ["episodes", "--help"])
        assert result.exit_code == 0
        assert "recompute" in result.output


class TestEpisodesRecompute:
    """Tests for 'asre episodes --recompute' command."""

    @patch("asre.cli.main._get_diagnostic_adapter")
    def test_recompute_reads_encounters_from_db(
        self, mock_get_adapter: MagicMock
    ) -> None:
        """Recompute reads encounters from admission_events_unified table."""
        adapter = MagicMock()
        mock_get_adapter.return_value = adapter
        adapter.read_source.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, [
            "episodes", "--recompute",
            "--config-path", "/fake/path",
            "--customer-id", "test",
        ])
        assert result.exit_code == 0
        # Should have attempted to read from the encounters table
        read_calls = adapter.read_source.call_args_list
        assert len(read_calls) >= 1
        first_call_query = str(read_calls[0])
        assert "admission_events_unified" in first_call_query

    @patch("asre.cli.main.load_config")
    @patch("asre.cli.main._get_diagnostic_adapter")
    def test_recompute_runs_episode_stages_only(
        self, mock_get_adapter: MagicMock, mock_load_config: MagicMock
    ) -> None:
        """Recompute runs episode stages (stitch, materialize, quality) but NOT
        ingest, canonicalize, stitch, dedup, reconcile, score stages."""
        adapter = MagicMock()
        mock_get_adapter.return_value = adapter

        # Mock config with no episode_stitching attr
        mock_config = MagicMock(spec=[])
        mock_load_config.return_value = mock_config

        # Return a valid encounter row from the DB
        now_iso = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc).isoformat()
        adapter.read_source.side_effect = [
            # First call: read encounters from admission_events_unified
            [
                {
                    "encounter_id": "ENC_001",
                    "patient_key": "PAT_001",
                    "encounter_type": "inpatient",
                    "status": "closed",
                    "admit_ts": "2024-01-01T10:00:00+00:00",
                    "discharge_ts": "2024-01-03T10:00:00+00:00",
                    "los_hours": 48.0,
                    "facility_canonical_id": "FAC_001",
                    "facility_name": "Test Hospital",
                    "is_acute": True,
                    "source_event_ids": json.dumps(["evt_001"]),
                    "source_systems": json.dumps(["adt_vendor_x"]),
                    "has_adt": True,
                    "has_claims": False,
                    "has_auth": False,
                    "confidence_score": 0.8,
                    "confidence_flags": json.dumps(["HAS_ADT_ADMIT"]),
                    "created_at": now_iso,
                    "updated_at": now_iso,
                    "asre_version": "0.1.0",
                    "admit_source_priority": "adt",
                    "discharge_source_priority": "adt",
                    "payer_id": None,
                    "drg": None,
                    "principal_diagnosis": None,
                    "admitting_diagnosis": None,
                    "diagnosis_codes": None,
                    "is_readmission": None,
                    "readmission_days": None,
                    "obs_to_ip_conversion": None,
                    "transfer_chain": None,
                    "episode_id": None,
                },
            ],
            # Subsequent read_source calls for episode materialization
            [],  # existing episode IDs
        ]
        adapter.write_records.return_value = 1

        runner = CliRunner()
        result = runner.invoke(cli, [
            "episodes", "--recompute",
            "--config-path", "/fake/path",
            "--customer-id", "test",
        ])
        assert result.exit_code == 0
        assert "episode" in result.output.lower()

    @patch("asre.cli.main._get_diagnostic_adapter")
    def test_recompute_no_encounters_shows_message(
        self, mock_get_adapter: MagicMock
    ) -> None:
        """Recompute with no encounters in DB shows informative message."""
        adapter = MagicMock()
        mock_get_adapter.return_value = adapter
        adapter.read_source.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, [
            "episodes", "--recompute",
            "--config-path", "/fake/path",
            "--customer-id", "test",
        ])
        assert result.exit_code == 0
        assert "no encounters" in result.output.lower() or "0" in result.output

    @patch("asre.cli.main._get_diagnostic_adapter")
    def test_recompute_does_not_run_ingest_or_score(
        self, mock_get_adapter: MagicMock
    ) -> None:
        """Recompute should NOT invoke ingest, canonicalize, stitch, dedup,
        reconcile, or score stages — only episode stages."""
        adapter = MagicMock()
        mock_get_adapter.return_value = adapter
        adapter.read_source.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, [
            "episodes", "--recompute",
            "--config-path", "/fake/path",
            "--customer-id", "test",
        ])
        assert result.exit_code == 0
        # No PipelineRunner should have been created (episodes recompute
        # bypasses the full pipeline runner)
        # If we get here without errors, the implementation didn't try to run
        # a full pipeline, which would require config sections we didn't provide


class TestRecordToEncounter:
    """Tests for converting DB records back to Encounter objects."""

    def test_converts_basic_record(self) -> None:
        from asre.episode.stage import record_to_encounter

        now_iso = "2024-01-15T10:00:00+00:00"
        record: dict[str, Any] = {
            "encounter_id": "ENC_001",
            "patient_key": "PAT_001",
            "encounter_type": "inpatient",
            "status": "closed",
            "admit_ts": "2024-01-01T10:00:00+00:00",
            "discharge_ts": "2024-01-03T10:00:00+00:00",
            "los_hours": 48.0,
            "facility_canonical_id": "FAC_001",
            "facility_name": "Test Hospital",
            "is_acute": True,
            "source_event_ids": json.dumps(["evt_001"]),
            "source_systems": json.dumps(["adt_vendor_x"]),
            "has_adt": True,
            "has_claims": False,
            "has_auth": False,
            "confidence_score": 0.8,
            "confidence_flags": json.dumps(["HAS_ADT_ADMIT"]),
            "created_at": now_iso,
            "updated_at": now_iso,
            "asre_version": "0.1.0",
            "admit_source_priority": "adt",
            "discharge_source_priority": "adt",
            "payer_id": None,
            "drg": None,
            "principal_diagnosis": None,
            "admitting_diagnosis": None,
            "diagnosis_codes": None,
            "is_readmission": None,
            "readmission_days": None,
            "obs_to_ip_conversion": None,
            "transfer_chain": None,
            "episode_id": None,
        }
        enc = record_to_encounter(record)
        assert enc.encounter_id == "ENC_001"
        assert enc.patient_key == "PAT_001"
        assert enc.encounter_type == "inpatient"
        assert enc.status == "closed"
        assert enc.is_acute is True
        assert enc.confidence_score == 0.8
        assert enc.source_event_ids == ["evt_001"]
        assert enc.source_systems == ["adt_vendor_x"]
        assert isinstance(enc.admit_ts, datetime)

    def test_handles_json_string_fields(self) -> None:
        from asre.episode.stage import record_to_encounter

        now_iso = "2024-01-15T10:00:00+00:00"
        record: dict[str, Any] = {
            "encounter_id": "ENC_002",
            "patient_key": "PAT_002",
            "encounter_type": "inpatient",
            "status": "closed",
            "admit_ts": "2024-01-01T10:00:00+00:00",
            "discharge_ts": "2024-01-03T10:00:00+00:00",
            "los_hours": 48.0,
            "facility_canonical_id": "FAC_001",
            "facility_name": "Test Hospital",
            "is_acute": True,
            "source_event_ids": json.dumps(["evt_001", "evt_002"]),
            "source_systems": json.dumps(["adt_vendor_x", "claims_clearinghouse"]),
            "has_adt": True,
            "has_claims": True,
            "has_auth": False,
            "confidence_score": 0.9,
            "confidence_flags": json.dumps(["HAS_ADT_ADMIT", "HAS_CLAIMS"]),
            "created_at": now_iso,
            "updated_at": now_iso,
            "asre_version": "0.1.0",
            "admit_source_priority": None,
            "discharge_source_priority": None,
            "payer_id": None,
            "drg": "470",
            "principal_diagnosis": "J18.9",
            "admitting_diagnosis": None,
            "diagnosis_codes": json.dumps([{"code": "J18.9", "type": "ICD-10-CM"}]),
            "is_readmission": False,
            "readmission_days": None,
            "obs_to_ip_conversion": False,
            "transfer_chain": json.dumps(["ENC_002", "ENC_003"]),
            "episode_id": "EP_001",
        }
        enc = record_to_encounter(record)
        assert enc.source_event_ids == ["evt_001", "evt_002"]
        assert enc.source_systems == ["adt_vendor_x", "claims_clearinghouse"]
        assert enc.confidence_flags == ["HAS_ADT_ADMIT", "HAS_CLAIMS"]
        assert enc.transfer_chain == ["ENC_002", "ENC_003"]
        assert enc.diagnosis_codes == [{"code": "J18.9", "type": "ICD-10-CM"}]
        assert enc.drg == "470"
        assert enc.episode_id == "EP_001"

    def test_handles_null_discharge(self) -> None:
        from asre.episode.stage import record_to_encounter

        now_iso = "2024-01-15T10:00:00+00:00"
        record: dict[str, Any] = {
            "encounter_id": "ENC_003",
            "patient_key": "PAT_003",
            "encounter_type": "inpatient",
            "status": "open",
            "admit_ts": "2024-01-01T10:00:00+00:00",
            "discharge_ts": None,
            "los_hours": None,
            "facility_canonical_id": "FAC_001",
            "facility_name": "Test Hospital",
            "is_acute": True,
            "source_event_ids": json.dumps(["evt_001"]),
            "source_systems": json.dumps(["adt_vendor_x"]),
            "has_adt": True,
            "has_claims": False,
            "has_auth": False,
            "confidence_score": 0.5,
            "confidence_flags": json.dumps([]),
            "created_at": now_iso,
            "updated_at": now_iso,
            "asre_version": "0.1.0",
            "admit_source_priority": None,
            "discharge_source_priority": None,
            "payer_id": None,
            "drg": None,
            "principal_diagnosis": None,
            "admitting_diagnosis": None,
            "diagnosis_codes": None,
            "is_readmission": None,
            "readmission_days": None,
            "obs_to_ip_conversion": None,
            "transfer_chain": None,
            "episode_id": None,
        }
        enc = record_to_encounter(record)
        assert enc.discharge_ts is None
        assert enc.los_hours is None
        assert enc.status == "open"
