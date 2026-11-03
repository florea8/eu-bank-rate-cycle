select
    exercise,
    csv_file,
    template,
    item,
    category,
    label,
    -- the same item's code in the exercise before, e.g. Item_TR_2024 for 2025
    previous_items ->> ('Item_TR_' || (exercise - 1)) as previous_exercise_item
from {{ source('raw', 'eba_items') }}
