{{
    config(
        materialized='table'
    )
}}

select
    encounter_id,
    event_id,
    event_type,
    event_ts,
    source_system,
    role_in_encounter
from {{ source('asre_raw', 'asre_encounters_detail') }}
