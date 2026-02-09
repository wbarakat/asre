-- Ensure admit_ts is before discharge_ts for all closed encounters.
-- Rows returned here indicate data quality issues.
select
    encounter_id,
    admit_ts,
    discharge_ts
from {{ ref('admission_events_unified') }}
where status = 'closed'
  and discharge_ts is not null
  and admit_ts > discharge_ts
