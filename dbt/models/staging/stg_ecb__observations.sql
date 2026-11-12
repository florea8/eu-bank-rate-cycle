select
    series_id,
    time_period::date as observation_date,
    obs_value as value
from {{ source('raw', 'ecb_observations') }}
