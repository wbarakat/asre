{{
    config(
        materialized='incremental',
        unique_key='encounter_id'
    )
}}

select
    encounter_id,
    patient_key,
    encounter_type,
    status,
    admit_ts,
    discharge_ts,
    los_hours,
    facility_canonical_id,
    facility_name,
    is_acute,
    source_event_ids,
    source_systems,
    has_adt,
    has_claims,
    has_auth,
    confidence_score,
    confidence_flags,
    admit_source_priority,
    discharge_source_priority,
    payer_id,
    drg,
    principal_diagnosis,
    admitting_diagnosis,
    diagnosis_codes,
    is_readmission,
    readmission_days,
    obs_to_ip_conversion,
    transfer_chain,
    episode_id,
    created_at,
    updated_at,
    asre_version
from {{ source('asre_raw', 'admission_events_unified') }}

{% if is_incremental() %}
where updated_at > (select max(updated_at) from {{ this }})
{% endif %}
