# Plan

Written 2026-10-29. A public, year-round, station-level forecasting service for the daily
high and low, with every forecast stored before settlement and scored every night against
the official climate report, the raw models, the NWS forecast and vendor forecasts. One
station first, Los Angeles International, ingested deep. A station is a row; the second
one is data, not code.

Two things come out of it. A verified record at station level, which nobody publishes for
free, and a repository whose history shows an AI building a scored service under tests,
gates and review.

## Decisions

| Question | Decision | Record |
|---|---|---|
| Architecture | Layered package, point-in-time store, one path, nothing at request time | 0001 |
| Keys | `received_at` in the key of observations and settlements; corrections are rows | 0002 |
| Issue cadence | Fixed local slots 00/06/12/18; lead to end of local day; evening slot to day 5 | 0003 |
| Model runs | One row per run and variable, horizon as an array; profiles as variables | 0004 |
| Station | KLAX first; every run kept hourly; profiles, NWS hourly grid, discussion, vendors | 0001 |
| Model set | GFS, ECMWF IFS, ICON (global); HRRR, NBM (CONUS); the NWS; vendor APIs | this file |
| Public science | Daily extremes and baselines public; other forecasters private behind the protocol | 0001 |
| Frontend | React, TypeScript, uPlot, ported station page; scorecard, discussion, profile panes | this file |

## Rules

- **Point in time, always.** `valid_at` and `received_at` on every row, UTC, tz-aware; every
  read takes `as_of`. Local day is derived in `localday` and nowhere else.
- **One path.** The live forecast function is the backtest function.
- **Nothing computes at request time.** Jobs write; routes read; the client computes nothing.
- **Frames have schemas.** pandera at every DataFrame boundary.
- **Feeds never raise.** Empty typed frame, heartbeat row, `/healthz` reports each feed.
- **A feature ships only with a line on the scorecard.**
- **Science is read by a person.** `features/` and `forecast/` stay small; their tests come
  first, written by a person.
- **Numbers exist only as CI output**, as rows in `docs/EXPERIMENTS.md`.

## Layout

```
pyproject.toml            one install; extras [service] [dev]
src/stationcast/
  config.py               settings from env, validated once
  localday.py             local day, slots, lead, targets per slot
  ingest/                 one module per feed; typed frames; never raises; heartbeat
  store/                  SQLAlchemy Core tables; Alembic; Store protocol (Postgres, in-memory)
  features/               pure functions, frame in, frame out
  forecast/               Forecaster protocol, baselines, issue()
  evaluate/               scoring, scorecard builder, golden backtest
  serve/                  FastAPI routes, read-only
client/                   React, TypeScript, uPlot; types generated from OpenAPI
scripts/                  seed_stations, ingest, score, openapi
tests/unit  tests/properties  tests/golden  tests/integration
docs/decisions/  docs/ARCHITECTURE.md  docs/EXPERIMENTS.md
alembic/  .github/workflows/
```

Dependencies point down only; `.importlinter` enforces it in CI.

## Database

Postgres on Neon, schema `stationcast`, Alembic. Append-only except `stations` (by hand)
and the derived `scores` and `scorecard`.

```
stations      station_id, network, name, lat, lon, elev, tz, settles, settlement_source,
              tier, active
observations  station_id, valid_at, received_at, source, var, value, precision
              PK (station_id, valid_at, source, var, received_at)
model_runs    model, station_id, run_at, received_at, source, var, step_h, values float4[]
              PK (model, station_id, run_at, var)
products      office, pil, issued_at, received_at, text
              PK (pil, issued_at)
settlements   station_id, local_day, target, value, source, received_at
              PK (station_id, local_day, target, received_at)
predictions   forecaster, version, station_id, target, local_day, as_of, received_at,
              quantiles jsonb, features jsonb
              PK (forecaster, version, station_id, target, local_day, as_of)
scores        forecaster, version, station_id, target, local_day, lead_h,
              mae, crps, brier jsonb, covered_90, computed_at
scorecard     forecaster, version, target, lead_h, period, n, mae, bias, built_at
heartbeat     feed, last_success, last_error, rows
```

## The model, in order

1. Baselines: each raw model's daily extreme, the NWS, each vendor, persistence,
   climatology. Published before any model.
2. A readable public model: inverse-MAE weighted consensus of the raw models with
   per-station bias and conformal bands. Coverage is monitored live: `covered_90` per lead
   bucket over a trailing 30 days must stay within 85 to 95, and a breach fails the nightly job.
3. Threshold events from the first scorer: crossing probabilities at fixed thresholds,
   scored with Brier and a reliability table.
4. Private forecasters behind the `Forecaster` protocol. Their rows and scores are public.
5. Observation impact as a scorecard row: any observation source added to a forecaster is
   scored with and without it, by lead. That is the only kind of assimilation claimed.

## Order of work

1. **Skeleton.** pyproject, CLAUDE.md, import contract, `localday` with its property test,
   CI, four ADRs, this plan, the feed table.
2. **Store and ingest.** Tables and migration; Postgres and in-memory stores under one read
   contract; feeds: Open-Meteo per model with profiles, NWS hourly grid, forecast
   discussion, IEM ASOS, IEM climate report, vendors; heartbeat; the hourly job; the
   lookahead property test.
3. **Features and baselines.** Person-written tests first; daily extremes; running extreme;
   `Forecaster` protocol; raw-model and persistence baselines; `issue()`.
4. **Evaluate.** Settle, score, scorecard; golden backtest committed; the hourly cron on.
5. **Serve and client.** Routes, OpenAPI types, the station page with scorecard,
   discussion and profile panes.
6. **Public model and thresholds.** Consensus with bands and the live coverage monitor.
7. **MCP server.** `forecast`, `observations`, `scorecard`, `profile`, `discussion`,
   `backtest`, all taking `as_of`; an agent runs the engines over these tools.
8. **More stations.** Rows, then the pooled model.

Targets after the high and low, in order: daily precipitation from the same climate
report, then hourly visibility and ceiling categories settled on METARs.
