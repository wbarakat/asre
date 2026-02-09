"""Tests for CLI health check integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from asre.cli.main import cli
from asre.observability.health import PipelineHealthState


class TestCliHealthCheck:
    def test_run_starts_health_server_and_passes_state(self) -> None:
        state = PipelineHealthState()
        server = MagicMock()
        thread = MagicMock()

        with patch(
            "asre.cli.main._start_health_server",
            return_value=(server, thread, state),
        ) as mock_start, patch(
            "asre.cli.main._create_pipeline_runner"
        ) as mock_create, patch(
            "asre.cli.main._check_env_or_exit"
        ), patch(
            "asre.cli.main._validate_license_or_exit"
        ):
            mock_runner = MagicMock()
            mock_runner.run.return_value = {
                "run_id": "test_run",
                "mode": "full",
                "stages_completed": 1,
            }
            mock_create.return_value = mock_runner

            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "run",
                    "--mode",
                    "full",
                    "--config-path",
                    "/tmp/config",
                    "--customer-id",
                    "test_customer",
                ],
            )

            assert result.exit_code == 0
            mock_start.assert_called_once()

            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs.get("health_state") is state
