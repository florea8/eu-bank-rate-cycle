-- Earlier exercises are keyed by two-digit year: LEI_Code_TE24 for 2024. The TE_24
-- "included" flags are left out: they are 1, Y or blank depending on the year, and
-- blank for every bank in 2023.
select
    exercise,
    lei_code,
    name,
    country,
    country_name,
    finrep,
    -- Fin_year_end is "31-Dec" or "31/12" text in some files and an Excel date in others
    case
        when fin_year_end ~ '^\d{4}-\d{2}-\d{2}' then extract(month from fin_year_end::date)
        when fin_year_end ~ '^\d{2}/\d{2}$' then split_part(fin_year_end, '/', 2)::integer
        else extract(month from to_date(fin_year_end, 'DD-Mon'))
    end::integer as fin_year_end_month,
    footnotes,
    previous_exercises ->> ('LEI_Code_TE' || (exercise - 2001)) as previous_exercise_lei_code
from {{ source('raw', 'eba_institutions') }}
