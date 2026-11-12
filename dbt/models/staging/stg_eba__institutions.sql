select
    exercise,
    lei_code,
    name,
    country,
    country_name,
    -- the bank's LEI in the exercise before, keyed by two-digit year: LEI_Code_TE24 for 2024
    previous_exercises ->> ('LEI_Code_TE' || (exercise - 2001)) as previous_exercise_lei_code
from {{ source('raw', 'eba_institutions') }}
