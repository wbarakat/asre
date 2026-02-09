-- Ensure confidence_score is between 0.0 and 1.0 for all encounters.
select
    encounter_id,
    confidence_score
from {{ ref('admission_events_unified') }}
where confidence_score is not null
  and (confidence_score < 0.0 or confidence_score > 1.0)
