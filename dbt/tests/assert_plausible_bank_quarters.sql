-- A margin outside -5% to 10% a year, or assets that are not positive, point to a unit
-- or item-mapping error rather than a real bank. Returns the rows that fail.
select lei_code, bank_name, period_end, net_interest_margin, total_assets
from {{ ref('fct_bank_quarter') }}
where net_interest_margin not between -0.05 and 0.10
   or total_assets <= 0
