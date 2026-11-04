-- Summing a bank's quarter_amount over its financial year must give the year-to-date
-- amount it reported. Returns the rows where it doesn't.
with year_to_date as (
    select
        *,
        (period_end + interval '1 day' - make_interval(months => 3 * n_quarters))::date
            as financial_year_start
    from {{ ref('int_eba__bank_values') }}
    where is_year_to_date
),

summed as (
    select
        lei_code,
        item_key,
        assets_fv,
        assets_stages,
        exposure,
        financial_instruments,
        financial_year_start,
        max(n_quarters) as last_quarter,
        count(*) as quarters_present,
        sum(quarter_amount) as sum_of_quarters,
        max(amount) filter (where n_quarters = 4) as full_year_amount
    from year_to_date
    group by 1, 2, 3, 4, 5, 6, 7
)

select *
from summed
where last_quarter = 4
  and quarters_present = 4
  and abs(sum_of_quarters - full_year_amount) > 0.01
