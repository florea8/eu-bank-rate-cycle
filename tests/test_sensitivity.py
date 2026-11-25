import numpy as np
import pandas as pd
import pytest

from bankcycle.analysis import sensitivity

QUARTERS = pd.date_range("2021-12-31", periods=8, freq="QE")
RATES = pd.Series([-0.5, 0.5, 2.0, 4.0, 4.0, 3.0, 2.5, 2.0], index=QUARTERS)


def test_rate_phases_split_at_last_peak_quarter():
    phases = sensitivity.rate_phases(RATES)

    assert phases["rate_up"].tolist() == [0.0, 1.0, 2.5, 4.5, 4.5, 4.5, 4.5, 4.5]
    assert phases["rate_down"].tolist() == [0.0, 0.0, 0.0, 0.0, 0.0, -1.0, -1.5, -2.0]


def _panel(banks: dict[str, tuple[float, float]], deposit_beta: float = 0.5) -> pd.DataFrame:
    """A panel where each bank's margin follows its (beta_up, beta_down) exactly, plus noise,
    and its deposit cost rises by deposit_beta per point of rate rises."""
    rng = np.random.default_rng(0)
    phases = sensitivity.rate_phases(RATES)
    rows = []
    for lei, (beta_up, beta_down) in banks.items():
        nim_pct = 1.0 + beta_up * phases["rate_up"] + beta_down * phases["rate_down"]
        nim_pct += rng.normal(0, 0.001, len(QUARTERS))
        for period, nim, rate, up in zip(QUARTERS, nim_pct, RATES, phases["rate_up"]):
            rows.append({"lei_code": lei, "bank_name": f"Bank {lei}", "country": "DE",
                         "period_end": period, "net_interest_margin": nim / 100,
                         "dfr_avg": rate, "total_assets": 10_000.0,
                         "overnight_deposit_share": 0.5, "deposits": 8_000.0,
                         "deposit_interest_expense": (0.2 + deposit_beta * up) / 400 * 8_000})
    return sensitivity.add_phases(pd.DataFrame(rows))


def test_bank_sensitivities_recovers_betas():
    panel = _panel({"A": (0.2, 0.1), "B": (0.1, 0.3)})

    banks = sensitivity.bank_sensitivities(panel).set_index("lei_code")

    assert banks.loc["A", "beta_up"] == pytest.approx(0.2, abs=1e-3)
    assert banks.loc["A", "beta_down"] == pytest.approx(0.1, abs=1e-3)
    # a 1-point cut costs beta_down percent of assets a year: 0.3% of 10,000 = 30
    assert banks.loc["B", "nii_change_per_100bp_cut"] == pytest.approx(-30, abs=0.1)
    assert banks.index[0] == "B"  # biggest loser first
    assert banks.loc["A", "deposit_beta"] == pytest.approx(0.5, abs=1e-6)


def test_pooled_sensitivity_averages_banks():
    panel = _panel({"A": (0.2, 0.1), "B": (0.1, 0.3)})

    fit = sensitivity.pooled_sensitivity(panel)

    assert fit.params["rate_up"] == pytest.approx(0.15, abs=1e-3)
    assert fit.params["rate_down"] == pytest.approx(0.2, abs=1e-3)
