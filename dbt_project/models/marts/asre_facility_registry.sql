{{
    config(
        materialized='incremental',
        unique_key='canonical_id'
    )
}}

select
    canonical_id,
    canonical_name,
    npi,
    ccn,
    facility_type,
    aliases,
    flags
from {{ source('asre_raw', 'asre_facility_registry') }}

{% if is_incremental() %}
where canonical_id not in (select canonical_id from {{ this }})
{% endif %}
