"""Tests for ASRE CLI skeleton (US-017)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from asre.cli.main import cli


class TestCliGroup:
    """Tests for the main CLI group."""

    def test_no_args_shows_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [])
        assert result.exit_code == 0
        assert "ASRE" in result.output
        assert "validate-config" in result.output
        assert "test-connection" in result.output

    def test_help_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "validate-config" in result.output
        assert "test-connection" in result.output


class TestValidateConfig:
    """Tests for the validate-config command."""

    _VALID_CONFIG_YAML = (
        "customer:\n"
        "  customer_id: test_customer\n"
        "  customer_name: Test Customer\n"
        "warehouse:\n"
        "  type: postgres\n"
        "  connection:\n"
        "    host: localhost\n"
        "    database: test\n"
    )

    def test_validate_config_success(self, tmp_path: Path) -> None:
        """Valid config prints success message."""
        customer_dir = tmp_path / "test_customer"
        customer_dir.mkdir()
        config_file = customer_dir / "config.yaml"
        config_file.write_text(self._VALID_CONFIG_YAML)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "validate-config",
            "--config-path", str(tmp_path),
            "--customer-id", "test_customer",
        ])
        assert result.exit_code == 0
        assert "valid" in result.output.lower() or "success" in result.output.lower()

    def test_validate_config_reads_env_vars(self, tmp_path: Path) -> None:
        """CLI reads ASRE_CONFIG_PATH and ASRE_CUSTOMER_ID from env."""
        customer_dir = tmp_path / "test_customer"
        customer_dir.mkdir()
        config_file = customer_dir / "config.yaml"
        config_file.write_text(self._VALID_CONFIG_YAML)

        runner = CliRunner()
        result = runner.invoke(cli, ["validate-config"], env={
            "ASRE_CONFIG_PATH": str(tmp_path),
            "ASRE_CUSTOMER_ID": "test_customer",
        })
        assert result.exit_code == 0
        assert "valid" in result.output.lower() or "success" in result.output.lower()

    def test_validate_config_flags_override_env(self, tmp_path: Path) -> None:
        """CLI flags override environment variables."""
        customer_dir = tmp_path / "test_customer"
        customer_dir.mkdir()
        config_file = customer_dir / "config.yaml"
        config_file.write_text(self._VALID_CONFIG_YAML)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "validate-config",
            "--config-path", str(tmp_path),
            "--customer-id", "test_customer",
        ], env={
            "ASRE_CONFIG_PATH": "/wrong/path",
            "ASRE_CUSTOMER_ID": "wrong_customer",
        })
        assert result.exit_code == 0
        assert "valid" in result.output.lower() or "success" in result.output.lower()

    def test_validate_config_missing_config_path(self) -> None:
        """Missing config path produces error."""
        runner = CliRunner()
        result = runner.invoke(cli, ["validate-config"])
        assert result.exit_code != 0

    def test_validate_config_missing_customer_id(self, tmp_path: Path) -> None:
        """Missing customer ID produces error."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "validate-config",
            "--config-path", str(tmp_path),
        ])
        assert result.exit_code != 0

    def test_validate_config_invalid_config(self, tmp_path: Path) -> None:
        """Invalid config prints errors."""
        customer_dir = tmp_path / "bad_customer"
        customer_dir.mkdir()
        config_file = customer_dir / "config.yaml"
        config_file.write_text("invalid_key: true\n")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "validate-config",
            "--config-path", str(tmp_path),
            "--customer-id", "bad_customer",
        ])
        assert result.exit_code != 0
        assert "error" in result.output.lower()

    def test_validate_config_nonexistent_directory(self) -> None:
        """Non-existent config directory prints error."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "validate-config",
            "--config-path", "/nonexistent/path",
            "--customer-id", "test",
        ])
        assert result.exit_code != 0
        assert "error" in result.output.lower() or "not found" in result.output.lower()


class TestTestConnection:
    """Tests for the test-connection command."""

    def test_test_connection_placeholder(self) -> None:
        """test-connection prints 'not yet implemented'."""
        runner = CliRunner()
        result = runner.invoke(cli, ["test-connection"])
        assert result.exit_code == 0
        assert "not yet implemented" in result.output.lower()

    def test_test_connection_in_help(self) -> None:
        """test-connection appears in help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "test-connection" in result.output


class TestEntryPoint:
    """Tests for CLI entry point configuration."""

    def test_entry_point_in_pyproject(self) -> None:
        """Entry point registered in pyproject.toml."""
        pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
        content = pyproject.read_text()
        assert 'asre = "asre.cli.main:cli"' in content
