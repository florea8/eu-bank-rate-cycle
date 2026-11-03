-- P&L amounts are year to date: n_quarters says how many quarters of the bank's
-- financial year they cover.
select
    exercise,
    lei_code,
    lei_code = 'XXXXXXXXXXXXXXXXXXXX' as is_aggregate,
    nsa as country,
    (to_date(period, 'YYYYMM') + interval '1 month - 1 day')::date as period_end,
    item,
    label,
    sheet,
    assets_fv,
    assets_stages,
    exposure,
    financial_instruments,
    amount,
    n_quarters::integer as n_quarters,
    fin_end_year as fin_end_year_code,
    footnote
from {{ source('raw', 'eba_tr_oth') }}
