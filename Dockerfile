FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN pip install --no-cache-dir setuptools wheel

# Copy project files
COPY pyproject.toml .
COPY asre/ asre/
COPY dbt_project/ dbt_project/
COPY customer_config/ customer_config/

# Build wheel
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

# Install warehouse adapter wheels
RUN pip wheel --no-cache-dir --wheel-dir /wheels \
    "snowflake-connector-python>=3.0,<4.0" \
    "google-cloud-bigquery>=3.0,<4.0" \
    "redshift-connector>=2.0,<3.0" \
    "dbt-snowflake>=1.7,<2.0" \
    "dbt-bigquery>=1.7,<2.0" \
    "dbt-redshift>=1.7,<2.0"

# --- Production image ---
FROM python:3.11-slim

WORKDIR /app

# Create non-root user (SPEC 14.2 security requirement)
RUN groupadd --gid 1000 asre && \
    useradd --uid 1000 --gid asre --shell /bin/bash --create-home asre

# Install wheels from builder
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

# Copy dbt project and config
COPY --chown=asre:asre dbt_project/ /app/dbt_project/
COPY --chown=asre:asre customer_config/ /app/customer_config/

# Switch to non-root user
USER asre

# Health check (US-105 will add HTTP endpoint; basic process check for now)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import asre; print('ok')"]

ENTRYPOINT ["asre"]
CMD ["--help"]
