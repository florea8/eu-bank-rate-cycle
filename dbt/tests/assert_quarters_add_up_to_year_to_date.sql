-- Summing a bank's quarter_amount over a full financial year must give the year-to-date
-- amount it reported for the fourth quarter. Returns the cases where it doesn't.
select
    lei_code,
    item_key,
    assets_fv,
    assets_stages,
    exposure,
    financial_instruments,
    financial_year_start,
    sum(quarter_amount) as sum_of_quarters,
    max(amount) filter (where n_quarters = 4) as full_year_amount
from {{ ref('int_eba__bank_values') }}
where is_year_to_date
group by 1, 2, 3, 4, 5, 6, 7
having count(*) = 4
   and abs(sum(quarter_amount) - max(amount) filter (where n_quarters = 4)) > 0.01
