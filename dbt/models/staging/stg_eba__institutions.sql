-- Earlier exercises are keyed by two-digit year: TE_24 and LEI_Code_TE24 for 2024.
with source as (
    select
        *,
        (exercise - 2001)::text as previous_yy
    from {{ source('raw', 'eba_institutions') }}
)

select
    exercise,
    lei_code,
    name,
    country,
    country_name,
    finrep,
    -- Fin_year_end is "31-Dec" text in some cells and an Excel date in others
    case
        when fin_year_end ~ '^\d{4}-\d{2}-\d{2}' then extract(month from fin_year_end::date)
        else extract(month from to_date(fin_year_end, 'DD-Mon'))
    end::integer as fin_year_end_month,
    footnotes,
    coalesce(previous_exercises ->> ('TE_' || previous_yy) = '1', false) as in_previous_exercise,
    previous_exercises ->> ('LEI_Code_TE' || previous_yy) as previous_exercise_lei_code
from source
