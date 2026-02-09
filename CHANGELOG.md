# Changelog

All notable changes to the ASRE (Admission Signal Reliability Engine) project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-05

### Added

- **Pipeline stages**: Full 12-stage pipeline -- Ingest, Canonicalize, Facility Normalize, Stitch, Dedup, Reconcile, Score, Materialize, Quality Check, Episode Stitch, Episode Materialize, Episode Quality
- **Warehouse support**: Postgres, Snowflake, BigQuery, and Redshift adapters with warehouse-aware DDL and migrations
- **Encounter stitching**: Time-window-based grouping with ED-to-IP merge, OBS-to-IP conversion, transfer chain detection, and configurable patient class transitions
- **Deduplication**: Event-level and encounter-level dedup with configurable match fields and time tolerance
- **Reconciliation**: Cross-source conflict resolution with configurable timestamp and classification priority
- **Confidence scoring**: Weighted signal scoring (0.0-1.0) with configurable weights and penalties per customer
- **Facility normalization**: String normalization, abbreviation expansion, NPI/CCN lookup, fuzzy matching via rapidfuzz
- **Episode processing**: Encounter grouping into care episodes with readmission detection and post-acute linkage
- **Quality gates**: Per-run metric computation, configurable warn/fail thresholds, webhook alerting (zero PHI)
- **Health checks**: HTTP `/health` endpoint, Docker HEALTHCHECK, CLI diagnostics
- **Checkpointing**: Stage-level checkpoint persistence with `--resume-run-id` CLI support
- **Auto-migrations**: 6 schema migrations with warehouse-aware DDL, auto-run on CLI startup
- **Audit logging**: Full pipeline modification trail in `asre_audit_log`
- **Structured logging**: JSON logging with stage context, run_id, record counts, duration
- **Dry-run mode**: `--dry-run` flag skips all DB writes and logs intended operations
- **CLI**: `asre run`, `asre validate-config`, `asre validate-env`, `asre test-connection`, `asre status`
- **Docker**: Multi-stage build, non-root user (uid 1000), health checks, ECS/Cloud Run compatible
- **dbt models**: 7 mart models (admission_events_unified, asre_encounters_detail, asre_facility_registry, asre_episodes, asre_audit_log, asre_run_metrics, asre_quality_metrics) with schema and singular tests
- **Configuration**: Pydantic-validated YAML with `${ENV_VAR}` substitution, per-customer config isolation
- **CI/CD**: GitHub Actions with unit tests, integration tests, mypy strict, dbt compile/test, Docker build, security scanning (pip-audit, bandit), test coverage reporting
- **Test suite**: 1,595+ tests across 107 files including golden-file regression, unit, and integration tests

### Output Tables

1. `admission_events_unified` -- Encounter-level unified view with confidence scores
2. `asre_encounters_detail` -- Event-level detail with role classifications
3. `asre_facility_registry` -- Canonical facility master with aliases, NPI, CCN
4. `asre_episodes` -- Episode-level view with encounter grouping
5. `asre_quality_metrics` -- Per-run quality metrics with pass/warn/fail status
6. `asre_audit_log` -- Pipeline modification audit trail
7. `asre_run_metrics` -- Per-stage timing and throughput metrics
