{{
    config(
        materialized='incremental',
        unique_key='episode_id'
    )
}}

select
    episode_id,
    patient_key,
    episode_type,
    episode_status,
    episode_start_ts,
    episode_end_ts,
    total_los_days,
    encounter_ids,
    encounter_count,
    facility_count,
    facility_sequence,
    includes_readmission,
    includes_post_acute,
    is_acute,
    principal_diagnosis,
    diagnosis_codes,
    confidence_score,
    created_at,
    updated_at
from {{ source('asre_raw', 'asre_episodes') }}

{% if is_incremental() %}
where updated_at > (select max(updated_at) from {{ this }})
{% endif %}
