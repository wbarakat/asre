"""Tests for US-010: Scaffold dbt project for PostgreSQL."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

DBT_PROJECT_DIR = Path(__file__).parent.parent.parent / "dbt_project"


class TestDbtProjectStructure:
    """Verify dbt project scaffolding meets acceptance criteria."""

    def test_dbt_project_yml_exists(self) -> None:
        assert (DBT_PROJECT_DIR / "dbt_project.yml").is_file()

    def test_dbt_project_name_is_asre(self) -> None:
        with open(DBT_PROJECT_DIR / "dbt_project.yml") as f:
            config = yaml.safe_load(f)
        assert config["name"] == "asre"

    def test_dbt_project_has_required_keys(self) -> None:
        with open(DBT_PROJECT_DIR / "dbt_project.yml") as f:
            config = yaml.safe_load(f)
        assert "version" in config
        assert "profile" in config
        assert "model-paths" in config

    def test_profiles_yml_exists(self) -> None:
        assert (DBT_PROJECT_DIR / "profiles.yml").is_file()

    def test_profiles_targets_postgres(self) -> None:
        with open(DBT_PROJECT_DIR / "profiles.yml") as f:
            profiles = yaml.safe_load(f)
        assert "asre" in profiles
        outputs = profiles["asre"]["outputs"]
        # At least one target should use postgres
        has_postgres = any(
            out.get("type") == "postgres" for out in outputs.values()
        )
        assert has_postgres

    def test_model_directories_exist(self) -> None:
        models_dir = DBT_PROJECT_DIR / "models"
        assert (models_dir / "staging").is_dir()
        assert (models_dir / "intermediate").is_dir()
        assert (models_dir / "marts").is_dir()

    def test_gitkeep_in_empty_model_dirs(self) -> None:
        models_dir = DBT_PROJECT_DIR / "models"
        for subdir in ["intermediate"]:
            assert (models_dir / subdir / ".gitkeep").is_file(), (
                f"Missing .gitkeep in models/{subdir}"
            )

    def test_dbt_tests_directory_exists(self) -> None:
        assert (DBT_PROJECT_DIR / "tests").is_dir()
