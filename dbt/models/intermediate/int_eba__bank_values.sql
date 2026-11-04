{{ config(materialized='table') }}

-- One row per bank, quarter, item and breakdown, with items matched across exercises.
-- P&L amounts are reported year to date; quarter_amount is the quarter on its own.
with bank_values as (
    select
        v.lei_code,
        b.name as bank_name,
        v.country,
        v.period_end,
        v.exercise,
        k.item_key,
        k.item_label,
        -- the SDD template, because tr_oth.csv has no Sheet column before 2023
        k.item_template as sheet,
        v.assets_fv,
        v.assets_stages,
        v.exposure,
        v.financial_instruments,
        v.amount,
        v.n_quarters,
        k.item_template = 'P&L' as is_year_to_date
    from {{ ref('stg_eba__tr_oth') }} as v
    inner join {{ ref('int_eba__item_keys') }} as k
        on k.exercise = v.exercise
       and k.item = v.item
    left join {{ ref('stg_eba__institutions') }} as b
        on b.exercise = v.exercise
       and b.lei_code = v.lei_code
    where not v.is_aggregate
)

select
    cur.*,
    case
        when not cur.is_year_to_date then null
        when cur.n_quarters = 1 then cur.amount
        else cur.amount - prev.amount
    end as quarter_amount
from bank_values as cur
left join bank_values as prev
    on cur.is_year_to_date
   and prev.lei_code = cur.lei_code
   and prev.item_key = cur.item_key
   and prev.assets_fv = cur.assets_fv
   and prev.assets_stages = cur.assets_stages
   and prev.exposure = cur.exposure
   and prev.financial_instruments = cur.financial_instruments
   and prev.n_quarters = cur.n_quarters - 1
   and prev.period_end = (cur.period_end + interval '1 day' - interval '3 months' - interval '1 day')::date
