-- Closed encounters should have a discharge timestamp.
select
    encounter_id,
    status,
    discharge_ts
from {{ ref('admission_events_unified') }}
where status = 'closed'
  and discharge_ts is null
