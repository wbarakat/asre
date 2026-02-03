{{
    config(
        materialized='table'
    )
}}

select
    run_id,
    metric_name,
    metric_value,
    warn_threshold,
    fail_threshold,
    status,
    computed_at
from {{ source('asre_raw', 'asre_quality_metrics') }}
