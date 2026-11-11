"""How much each bank's net interest margin moved with the ECB deposit rate, separately
while rates rose and while they fell."""
import logging
import warnings
from pathlib import Path

import pandas as pd
import psycopg
import statsmodels.formula.api as smf
from statsmodels.tools.sm_exceptions import ValueWarning

from bankcycle import db
from bankcycle.logging_conf import log_step
from bankcycle.settings import REPO_ROOT

log = logging.getLogger(__name__)

REPORTS_DIR = REPO_ROOT / "reports"

PANEL_QUERY = """
SELECT lei_code, bank_name, country, period_end, net_interest_margin, dfr_avg, total_assets,
       overnight_deposit_share
FROM marts.fct_bank_quarter
WHERE in_balanced_panel AND net_interest_margin IS NOT NULL
ORDER BY lei_code, period_end
"""


def load_panel(conn: psycopg.Connection) -> pd.DataFrame:
    cur = conn.execute(PANEL_QUERY)
    panel = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    numeric = ["net_interest_margin", "dfr_avg", "total_assets", "overnight_deposit_share"]
    panel[numeric] = panel[numeric].astype(float)
    panel["period_end"] = pd.to_datetime(panel["period_end"])
    return panel


def rate_phases(rates: pd.Series) -> pd.DataFrame:
    """Split a quarterly rate path into its rise and its fall, in percentage points.

    rate_up is the rise since the first quarter, held at the peak afterwards. rate_down is
    the fall since the last quarter at the peak: zero until then, negative after.
    """
    rates = rates.sort_index()
    peak_rate = rates.max()
    peak = rates[rates == peak_rate].index[-1]
    after_peak = rates.index > peak
    return pd.DataFrame(
        {
            "rate_up": rates.where(~after_peak, peak_rate) - rates.iloc[0],
            "rate_down": (rates - peak_rate).where(after_peak, 0.0),
        }
    )


def add_phases(panel: pd.DataFrame) -> pd.DataFrame:
    """Panel with rate_up, rate_down and the margin in percent (nim_pct)."""
    rates = panel.groupby("period_end")["dfr_avg"].first()
    out = panel.join(rate_phases(rates), on="period_end")
    out["nim_pct"] = 100 * out["net_interest_margin"]
    return out


def bank_sensitivities(panel: pd.DataFrame) -> pd.DataFrame:
    """One OLS per bank: nim_pct ~ rate_up + rate_down.

    beta_up is the margin gained per point of rate rises. beta_down is the margin lost per
    point of rate cuts (rate_down is negative, so a positive beta_down means the margin
    fell with the cuts). nii_change_per_100bp_cut is the yearly net interest income a
    further 1-point cut would cost at the latest balance sheet, in EUR million.
    """
    rows = []
    for lei_code, bank in panel.groupby("lei_code"):
        fit = smf.ols("nim_pct ~ rate_up + rate_down", data=bank).fit()
        latest = bank.sort_values("period_end").iloc[-1]
        rows.append(
            {
                "lei_code": lei_code,
                "bank_name": latest["bank_name"],
                "country": latest["country"],
                "quarters": len(bank),
                "beta_up": fit.params["rate_up"],
                "beta_up_se": fit.bse["rate_up"],
                "beta_down": fit.params["rate_down"],
                "beta_down_se": fit.bse["rate_down"],
                "r_squared": fit.rsquared,
                "total_assets": latest["total_assets"],
                "overnight_deposit_share": latest["overnight_deposit_share"],
                "nii_change_per_100bp_cut": -fit.params["rate_down"] / 100 * latest["total_assets"],
            }
        )
    return pd.DataFrame(rows).sort_values("nii_change_per_100bp_cut").reset_index(drop=True)


def pooled_sensitivity(panel: pd.DataFrame):
    """The same model over all banks, with a fixed effect per bank and standard errors
    clustered by bank."""
    groups = panel["lei_code"].astype("category").cat.codes
    return smf.ols("nim_pct ~ rate_up + rate_down + C(lei_code)", data=panel).fit(
        cov_type="cluster", cov_kwds={"groups": groups}
    )


def run(reports_dir: Path = REPORTS_DIR) -> None:
    reports_dir.mkdir(exist_ok=True)
    with db.connect() as conn:
        panel = add_phases(load_panel(conn))

    with log_step(log, "analyze", file="bank_sensitivity.csv") as ctx:
        banks = bank_sensitivities(panel)
        banks.to_csv(reports_dir / "bank_sensitivity.csv", index=False, float_format="%.6g")
        ctx["rows"] = len(banks)

    with log_step(log, "analyze", file="pooled_sensitivity.txt"):
        fit = pooled_sensitivity(panel)
        with warnings.catch_warnings():
            # The summary's joint F-test over all bank dummies is rank deficient under
            # clustering. Only the rate coefficients are reported.
            warnings.simplefilter("ignore", ValueWarning)
            summary = fit.summary2(float_format="%.4f").tables[1].loc[["rate_up", "rate_down"]]
        (reports_dir / "pooled_sensitivity.txt").write_text(
            f"nim_pct ~ rate_up + rate_down + bank fixed effects\n"
            f"{panel['lei_code'].nunique()} banks, {len(panel)} bank-quarters, "
            f"standard errors clustered by bank\n\n{summary.to_string()}\n",
            encoding="utf-8",
        )
