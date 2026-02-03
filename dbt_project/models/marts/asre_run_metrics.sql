{{
    config(
        materialized='table'
    )
}}

select
    run_id,
    stage_name,
    started_at,
    completed_at,
    records_in,
    records_out,
    errors,
    status
from {{ source('asre_raw', 'asre_run_metrics') }}
