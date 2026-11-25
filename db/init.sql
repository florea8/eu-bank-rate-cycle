CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS intermediate;
CREATE SCHEMA IF NOT EXISTS marts;

CREATE TABLE IF NOT EXISTS raw.ecb_observations (
    series_id   text NOT NULL,
    series_key  text NOT NULL,
    time_period text NOT NULL,
    obs_value   double precision,
    obs_status  text,
    title       text,
    loaded_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (series_key, time_period)
);

CREATE TABLE IF NOT EXISTS raw.eba_tr_oth (
    exercise              integer NOT NULL,
    lei_code              text NOT NULL,
    nsa                   text,
    period                text NOT NULL,
    item                  text NOT NULL,
    label                 text,
    assets_fv             text NOT NULL,
    assets_stages         text NOT NULL,
    exposure              text NOT NULL,
    financial_instruments text NOT NULL,
    amount                numeric,
    fin_end_year          text,
    n_quarters            text,
    footnote              text,
    sheet_row             text,
    sheet_column          text,
    sheet                 text,
    source_sha256         text NOT NULL,
    loaded_at             timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (exercise, lei_code, period, item,
                 assets_fv, assets_stages, exposure, financial_instruments)
);

CREATE TABLE IF NOT EXISTS raw.eba_items (
    exercise       integer NOT NULL,
    csv_file       text NOT NULL,
    template       text NOT NULL,
    item           text NOT NULL,
    category       text,
    label          text,
    collection     text,
    previous_items jsonb NOT NULL,
    source_sha256  text NOT NULL,
    loaded_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (exercise, csv_file, template, item)
);

CREATE TABLE IF NOT EXISTS raw.eba_institutions (
    exercise           integer NOT NULL,
    lei_code           text NOT NULL,
    country            text,
    country_name       text,
    name               text,
    finrep             text,
    fin_year_end       text,
    footnotes          text,
    previous_exercises jsonb NOT NULL,
    source_sha256      text NOT NULL,
    loaded_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (exercise, lei_code)
);
