select
    series_id,
    series_key,
    time_period::date as observation_date,
    obs_value as value,
    obs_status as status,
    title
from {{ source('raw', 'ecb_observations') }}
