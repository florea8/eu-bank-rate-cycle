-- One row per bank and quarter with the figures the analysis uses, in EUR million.
-- Flows (interest, income, profit) cover the quarter alone; balances are at quarter end.
-- not materialized: each use reads the table with its statistics (see the analyze in
-- int_eba__bank_values), so Postgres picks a 1 s plan instead of a 20 s one
with bank_values as not materialized (
    select * from {{ ref('int_eba__bank_values') }}
),

totals as (
    select
        lei_code,
        period_end,
        sum(quarter_amount) filter (where item_key = '2520301') as interest_income,
        sum(quarter_amount) filter (where item_key = '2520304') as interest_expense,
        sum(quarter_amount) filter (where item_key = '2520305') as deposit_interest_expense,
        sum(quarter_amount) filter (where item_key = '2520316') as total_operating_income,
        sum(quarter_amount) filter (where item_key = '2520332') as profit_before_tax,
        sum(amount) filter (where item_key = '2521010') as total_assets,
        sum(amount) filter (where item_key = '2521216') as total_equity,
        sum(amount) filter (where item_key = '2520140') as cet1_ratio
    from bank_values
    where assets_fv = '0'
      and assets_stages = '0'
      and exposure = '0'
      and financial_instruments = '0'
    group by 1, 2
),

-- Deposits are only reported by counterparty sector, so the total is their sum.
deposits as (
    select
        lei_code,
        period_end,
        sum(amount) filter (where financial_instruments = '30') as deposits,
        sum(amount) filter (where financial_instruments = '30' and exposure = '401')
            as household_deposits,
        sum(amount) filter (where financial_instruments = '31') as overnight_deposits
    from bank_values
    where item_key = '2521215'
      and exposure <> '0'
    group by 1, 2
),

-- Name and country as given in the bank's latest exercise.
banks as (
    select distinct on (lei_code)
        lei_code,
        bank_name,
        country
    from bank_values
    order by lei_code, period_end desc
),

rates as (
    select
        (date_trunc('quarter', observation_date) + interval '3 months - 1 day')::date
            as period_end,
        avg(value) as dfr_avg,
        (array_agg(value order by observation_date desc))[1] as dfr_end
    from {{ ref('stg_ecb__observations') }}
    where series_id = 'dfr'
    group by 1
),

bank_quarters as (
    select
        t.lei_code,
        b.bank_name,
        b.country,
        t.period_end,
        t.interest_income,
        t.interest_expense,
        t.interest_income - t.interest_expense as net_interest_income,
        t.deposit_interest_expense,
        t.total_operating_income,
        t.profit_before_tax,
        t.total_assets,
        t.total_equity,
        d.deposits,
        d.household_deposits,
        d.overnight_deposits,
        t.cet1_ratio,
        r.dfr_avg,
        r.dfr_end
    from totals as t
    inner join banks as b on b.lei_code = t.lei_code
    left join deposits as d
        on d.lei_code = t.lei_code
       and d.period_end = t.period_end
    left join rates as r on r.period_end = t.period_end
),

-- Banks with net interest income in every quarter of the panel, so totals compare
-- the same banks over time.
panel as (
    select
        lei_code,
        count(*) filter (where net_interest_income is not null)
            = (select count(distinct period_end) from bank_quarters
               where period_end >= '{{ var("panel_start") }}')
            as in_balanced_panel
    from bank_quarters
    where period_end >= '{{ var("panel_start") }}'
    group by 1
)

select
    q.*,
    4 * q.net_interest_income / nullif(q.total_assets, 0) as net_interest_margin,
    q.overnight_deposits / nullif(q.deposits, 0) as overnight_deposit_share,
    coalesce(p.in_balanced_panel, false) as in_balanced_panel
from bank_quarters as q
left join panel as p on p.lei_code = q.lei_code
-- earlier quarters have no quarter-only P&L, so their totals would look like a collapse
where q.period_end >= '{{ var("panel_start") }}'
