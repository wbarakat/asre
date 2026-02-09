-- Ensure episode confidence_score is between 0.0 and 1.0.
select
    episode_id,
    confidence_score
from {{ ref('asre_episodes') }}
where confidence_score is not null
  and (confidence_score < 0.0 or confidence_score > 1.0)
