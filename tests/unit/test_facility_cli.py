"""Tests for facility CLI commands (US-042)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from asre.cli.main import cli


class TestFacilitiesCommandGroup:
    """Tests for the facilities command appearing in CLI help."""

    def test_facilities_in_help(self) -> None:
        """facilities command appears in help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "facilities" in result.output

    def test_facilities_help(self) -> None:
        """facilities --help shows subcommands."""
        runner = CliRunner()
        result = runner.invoke(cli, ["facilities", "--help"])
        assert result.exit_code == 0
        assert "unresolved" in result.output.lower()
        assert "resolve" in result.output.lower()


class TestFacilitiesUnresolved:
    """Tests for asre facilities --unresolved command."""

    def test_unresolved_lists_flagged_facilities(self) -> None:
        """--unresolved lists facilities flagged FACILITY_NEW_UNREVIEWED."""
        mock_adapter = MagicMock()
        # Simulate reading from DB: two facilities, one unresolved
        mock_adapter.read_source.return_value = [
            {
                "canonical_id": "FAC_001",
                "canonical_name": "St. Mary's Hospital",
                "facility_type": "acute",
                "npi": None,
                "ccn": None,
                "aliases": "[]",
                "flags": '["FACILITY_NEW_UNREVIEWED"]',
            },
            {
                "canonical_id": "FAC_002",
                "canonical_name": "Good Sam Medical Center",
                "facility_type": "acute",
                "npi": "1234567890",
                "ccn": None,
                "aliases": "[]",
                "flags": "[]",
            },
        ]

        with patch("asre.cli.main._get_facility_adapter", return_value=mock_adapter):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "facilities", "--unresolved",
                "--config-path", "/fake/path",
                "--customer-id", "test",
            ])

        assert result.exit_code == 0
        assert "FAC_001" in result.output
        assert "St. Mary" in result.output
        # FAC_002 should NOT appear (not unresolved)
        assert "FAC_002" not in result.output

    def test_unresolved_no_results(self) -> None:
        """--unresolved with no unresolved facilities shows message."""
        mock_adapter = MagicMock()
        mock_adapter.read_source.return_value = [
            {
                "canonical_id": "FAC_002",
                "canonical_name": "Good Sam Medical Center",
                "facility_type": "acute",
                "npi": "1234567890",
                "ccn": None,
                "aliases": "[]",
                "flags": "[]",
            },
        ]

        with patch("asre.cli.main._get_facility_adapter", return_value=mock_adapter):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "facilities", "--unresolved",
                "--config-path", "/fake/path",
                "--customer-id", "test",
            ])

        assert result.exit_code == 0
        assert "no unresolved" in result.output.lower()

    def test_unresolved_multiple_facilities(self) -> None:
        """--unresolved lists multiple unresolved facilities."""
        mock_adapter = MagicMock()
        mock_adapter.read_source.return_value = [
            {
                "canonical_id": "FAC_AAA",
                "canonical_name": "Unknown Hospital A",
                "facility_type": None,
                "npi": None,
                "ccn": None,
                "aliases": "[]",
                "flags": '["FACILITY_NEW_UNREVIEWED"]',
            },
            {
                "canonical_id": "FAC_BBB",
                "canonical_name": "Unknown Hospital B",
                "facility_type": None,
                "npi": None,
                "ccn": None,
                "aliases": "[]",
                "flags": '["FACILITY_NEW_UNREVIEWED"]',
            },
        ]

        with patch("asre.cli.main._get_facility_adapter", return_value=mock_adapter):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "facilities", "--unresolved",
                "--config-path", "/fake/path",
                "--customer-id", "test",
            ])

        assert result.exit_code == 0
        assert "FAC_AAA" in result.output
        assert "FAC_BBB" in result.output

    def test_unresolved_requires_config(self) -> None:
        """--unresolved requires config-path and customer-id."""
        runner = CliRunner()
        result = runner.invoke(cli, ["facilities", "--unresolved"])
        assert result.exit_code != 0


class TestFacilitiesResolve:
    """Tests for asre facilities resolve <id> command."""

    def test_resolve_maps_to_existing(self) -> None:
        """resolve maps unresolved facility to existing canonical ID."""
        mock_adapter = MagicMock()
        # First call: read the facility to resolve
        # Second call: read target facility to verify it exists
        mock_adapter.read_source.side_effect = [
            # Read unresolved facility
            [{
                "canonical_id": "FAC_NEW_001",
                "canonical_name": "Unknown Hospital",
                "facility_type": None,
                "npi": None,
                "ccn": None,
                "aliases": '["UNKNOWN HOSPITAL"]',
                "flags": '["FACILITY_NEW_UNREVIEWED"]',
            }],
            # Read target facility
            [{
                "canonical_id": "FAC_001",
                "canonical_name": "St. Mary's Hospital",
                "facility_type": "acute",
                "npi": "1234567890",
                "ccn": None,
                "aliases": '["ST MARYS"]',
                "flags": "[]",
            }],
        ]

        with patch("asre.cli.main._get_facility_adapter", return_value=mock_adapter), \
             patch("asre.cli.main._validate_license_or_exit"):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "facilities",
                "--config-path", "/fake/path",
                "--customer-id", "test",
                "resolve", "FAC_NEW_001",
                "--target", "FAC_001",
            ])

        assert result.exit_code == 0
        assert "FAC_NEW_001" in result.output
        assert "FAC_001" in result.output

    def test_resolve_unknown_source_id(self) -> None:
        """resolve with unknown source facility ID shows error."""
        mock_adapter = MagicMock()
        mock_adapter.read_source.return_value = []

        with patch("asre.cli.main._get_facility_adapter", return_value=mock_adapter), \
             patch("asre.cli.main._validate_license_or_exit"):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "facilities",
                "--config-path", "/fake/path",
                "--customer-id", "test",
                "resolve", "FAC_NONEXISTENT",
                "--target", "FAC_001",
            ])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_resolve_unknown_target_id(self) -> None:
        """resolve with unknown target facility ID shows error."""
        mock_adapter = MagicMock()
        mock_adapter.read_source.side_effect = [
            # Source exists
            [{
                "canonical_id": "FAC_NEW_001",
                "canonical_name": "Unknown Hospital",
                "facility_type": None,
                "npi": None,
                "ccn": None,
                "aliases": "[]",
                "flags": '["FACILITY_NEW_UNREVIEWED"]',
            }],
            # Target not found
            [],
        ]

        with patch("asre.cli.main._get_facility_adapter", return_value=mock_adapter), \
             patch("asre.cli.main._validate_license_or_exit"):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "facilities",
                "--config-path", "/fake/path",
                "--customer-id", "test",
                "resolve", "FAC_NEW_001",
                "--target", "FAC_NONEXISTENT",
            ])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_resolve_requires_target(self) -> None:
        """resolve requires --target option."""
        mock_adapter = MagicMock()
        with patch("asre.cli.main._get_facility_adapter", return_value=mock_adapter):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "facilities",
                "--config-path", "/fake/path",
                "--customer-id", "test",
                "resolve", "FAC_NEW_001",
            ])
        assert result.exit_code != 0

    def test_resolve_requires_config(self) -> None:
        """resolve requires config-path and customer-id."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "facilities",
            "resolve", "FAC_NEW_001",
            "--target", "FAC_001",
        ])
        assert result.exit_code != 0
