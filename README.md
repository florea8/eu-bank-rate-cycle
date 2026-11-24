# EU banks and the rate cycle

How much did the 2022–2025 ECB rate cycle move net interest income across EU banks, and which banks lose most as rates fall?

**Data:** 82 EU banks reporting in every EBA Transparency Exercise from 2021 to 2025, with quarters from Q4 2020 to Q2 2025. Bank-level data ends at Jun 2025, because the EBA discontinued the Transparency Exercise after the 2025 edition.

## Findings

- **Rate rises lifted net interest income by about a quarter.** Quarterly NII across the 82 banks rose from EUR 70.1bn in Q2 2022, before the first hike, to EUR 88.8bn in Q1 2024 (+27%).
- **Cuts have taken back little so far.** By Q2 2025 the average deposit rate was 1.7 points below its peak, but quarterly NII was only 4% below its high, at EUR 85.2bn.
- **Each point of the rate moves the margin by about 0.13–0.15 pp.** Within banks, a 1-point rise went with a 0.15 pp higher net interest margin (95% CI 0.12–0.18), and a 1-point cut with a 0.13 pp lower one (95% CI 0.09–0.16). Margins give back slightly less than they gained, but the difference is within the error.
- **A further 1-point cut would cost these banks about EUR 18bn of NII a year.** Banco Santander (EUR 2.6bn), ING (EUR 1.4bn) and Groupe Crédit Agricole (EUR 1.2bn) lose most in euros, because they are large and have a high beta. A higher share of overnight deposits goes only weakly with a larger loss (correlation 0.27).

Full results: [reports/bank_sensitivity.csv](reports/bank_sensitivity.csv) (one row per bank) and [reports/pooled_sensitivity.txt](reports/pooled_sensitivity.txt).

## Method

- Net interest margin (NIM) is annualised quarterly NII over total assets. The ECB rate is the deposit facility rate averaged over each quarter.
- The rate path is split into `rate_up`, the rise up to the peak, and `rate_down`, the fall after it, so rises and cuts each get their own slope.
- Per bank: `nim_pct ~ rate_up + rate_down`. Pooled: the same model with a fixed effect per bank and standard errors clustered by bank.
- The NII cost of a 1-point cut is the bank's cut slope applied to its latest total assets.
- Limits: 19–20 quarters per bank, no control for loan growth, hedging or fees, and the cutting phase is only four quarters long.

## Run it

Needs Python 3.11+ and PostgreSQL 16, either local or from `docker compose up -d`.

```
cp .env.example .env            # then set PGPASSWORD
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
bankcycle db-check
bankcycle ingest                # ECB rates and EBA files, into the raw schema
bankcycle dbt build             # staging, intermediate and marts.fct_bank_quarter, with tests
bankcycle analyze               # writes reports/
pytest
```

The EBA refuses scripted downloads, so its files are saved by hand into `data/raw/eba/<year>/`. `bankcycle ingest` prints the URL of any missing file and checks each one against its pinned checksum in [config/sources.yaml](config/sources.yaml).

## Stack

Python for ingestion and checks, PostgreSQL and dbt for modelling, statsmodels for the analysis. A Power BI dashboard on `marts.fct_bank_quarter` is next.
