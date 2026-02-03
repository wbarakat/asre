{{
    config(
        materialized='table'
    )
}}

select
    log_id,
    run_id,
    timestamp,
    action,
    entity_type,
    entity_id,
    detail
from {{ source('asre_raw', 'asre_audit_log') }}
