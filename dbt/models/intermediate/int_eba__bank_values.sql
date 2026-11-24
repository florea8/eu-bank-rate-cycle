-- analyze: fct_bank_quarter takes 20 s instead of 1 s if Postgres has no statistics
-- on this freshly built table
{{ config(materialized='table', post_hook='analyze {{ this }}') }}

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
        v.assets_fv,
        v.assets_stages,
        v.exposure,
        v.financial_instruments,
        v.amount,
        v.n_quarters,
        k.item_template = 'P&L' as is_year_to_date,
        -- first day of the bank's financial year that a year-to-date amount counts from
        (v.period_end + 1 - make_interval(months => 3 * v.n_quarters))::date
            as financial_year_start
    from {{ ref('stg_eba__tr_oth') }} as v
    inner join {{ ref('int_eba__item_keys') }} as k
        on k.exercise = v.exercise
       and k.item = v.item
    left join {{ ref('stg_eba__institutions') }} as b
        on b.exercise = v.exercise
       and b.lei_code = v.lei_code
    where not v.is_aggregate
      and k.item_key in ('{{ var("items") | join("', '") }}')
)

select
    *,
    case
        when not is_year_to_date then null
        when n_quarters = 1 then amount
        when lag(n_quarters) over same_year = n_quarters - 1
            then amount - lag(amount) over same_year
    end as quarter_amount
from bank_values
window same_year as (
    partition by
        lei_code, item_key, assets_fv, assets_stages, exposure, financial_instruments,
        financial_year_start
    order by n_quarters
)
