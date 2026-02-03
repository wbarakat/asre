{{
    config(
        materialized='table'
    )
}}

select
    log_id,
    run_id,
    {{ quote_identifier('timestamp') }} as {{ quote_identifier('timestamp') }},
    action,
    entity_type,
    entity_id,
    detail
from {{ source('asre_raw', 'asre_audit_log') }}
