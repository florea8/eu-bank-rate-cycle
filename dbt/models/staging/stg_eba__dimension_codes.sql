select
    exercise,
    dimension,
    code,
    trim(label) as label
from {{ source('raw', 'eba_dimension_codes') }}
