-- Ensure every detail record references an existing encounter.
select
    d.encounter_id,
    d.event_id
from {{ ref('asre_encounters_detail') }} d
left join {{ ref('admission_events_unified') }} u
    on d.encounter_id = u.encounter_id
where u.encounter_id is null
