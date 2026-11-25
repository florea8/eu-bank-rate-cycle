select
    exercise,
    lei_code,
    name,
    country,
    country_name
from {{ source('raw', 'eba_institutions') }}
