# 0004. One row per model run and variable, with the horizon as an array

Date: 2026-10-29
Status: accepted

## Context

Six models to five days at four or more runs a day, one row per hour per variable, is tens
of thousands of rows a day at 165 stations. Pressure-level profiles multiply that. Open-Meteo,
the source for five of the models, does not report which model cycle it served.

## Decision

`model_runs` holds one row per `(model, station_id, run_at, var)` with `step_h` and a
`float4[]` of values; element `i` is valid at `run_at + (step_h + i)` hours. Surface and
pressure-level variables share the table through `var` names such as `t2m`, `td2m`,
`cloud`, `t_850`, `z_500`, `wspd_925`. Vendor daily forecasts use `var = tmax | tmin` with
one element per target day.

`run_at` for Open-Meteo rows is the hour the feed was fetched, since the cycle is not
reported. `received_at` is the fetch time. A `source` column marks live rows apart from any
backfill, whose `received_at` is an assumption documented beside the ingest module.

For the first station every run is kept hourly. When stations are added at scale, ingest
keeps the latest run per model per slot and rows older than 18 months roll off to parquet.
`predictions` never rolls off; it is the record of what was known.

## Consequences

Row counts fall by about an order of magnitude against hourly rows. Point-in-time reads
pick the latest `run_at` per model with `received_at <= as_of`. The true cycle is unknown
for Open-Meteo models; a GRIB-based feed can fill it later for the models that matter.

## Alternatives rejected

- Daily extremes only: no diurnal shape, no profiles, no later features.
- Hourly rows as a wide table: largest table by far, no gain in query simplicity.
