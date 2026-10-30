# Plan

Written 2026-10-29. A public, year-round, station-level forecasting service for the daily
high and low, with every forecast stored before settlement and scored every night against
the official climate report, the raw models, the NWS forecast and vendor forecasts. Stations
are rows in `data/stations.csv`. The first set is six deep stations chosen for different
regimes, Los Angeles, Miami, Chicago Midway, Austin, New York Central Park and Washington
National, ingested with every model run, profiles, the discussion, vendor forecasts and
public market prices where a market exists, plus the thirteen other ASOS stations of the
Los Angeles basin at slot depth as the first neighbour ring. Depth and settlement are
columns on the row, not branches of the code. A wider set is more rows.

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
| Stations | Rows in `data/stations.csv`; six deep stations in different regimes (KLAX, KMIA, KMDW, KAUS, KNYC, KDCA) plus the Los Angeles basin ring at slot depth | 0001, 0005 |
| Markets | Public bracket prices sampled at slots; market-implied probability is a scorecard baseline; nothing that trades enters | 0005 |
| Model set | GFS, ECMWF IFS, ICON (global); HRRR, NBM (CONUS); the NWS; vendor APIs | this file |
| Open source | All code public. Private inputs (dense station networks, keys) enter by configuration; every forecaster implements one `Forecaster` protocol | 0001 |
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
src/camanchaca-demo/
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

Postgres on Neon, schema `camanchaca_demo`, Alembic. Append-only except `stations` (by hand)
and the derived `scores` and `scorecard`.

```
stations      station_id, network, name, lat, lon, elev, tz, settles, settlement_source,
              tier, depth (slot | deep), active
observations  station_id, valid_at, received_at, source, var, value, precision
              PK (station_id, valid_at, source, var, received_at)
model_runs    model, station_id, run_at, received_at, source, var, step_h, values float4[]
              PK (model, station_id, run_at, var)
products      office, pil, issued_at, received_at, text
              PK (pil, issued_at)
markets       station_id, local_day, ticker, bracket_lo, bracket_hi, as_of, received_at,
              yes_bid, yes_ask, last_price
              PK (ticker, as_of)
settlements   station_id, local_day, target, value, source, received_at
              PK (station_id, local_day, target, received_at)
predictions   forecaster, version, station_id, target, local_day, as_of, received_at,
              quantiles jsonb, features jsonb
              PK (forecaster, version, station_id, target, local_day, as_of)
scores        forecaster, version, station_id, target, local_day, lead_h,
              mae, crps, brier jsonb, bracket_brier, covered_90, computed_at
scorecard     forecaster, version, target, lead_h, period, n, mae, bias, built_at
heartbeat     feed, last_success, last_error, rows
```

## The model, in order

1. Baselines: each raw model's daily extreme, the NWS, each vendor, persistence,
   climatology. Published before any model.
2. Two public models, open source and read line by line: an inverse-MAE weighted consensus
   of the raw models with per-station bias and conformal bands, and a small gradient-boosted
   quantile model on public features only (the raw models, their spread, lead, the running
   extreme), pooled across stations with conformal bands. Coverage is monitored live: `covered_90` per lead
   bucket over a trailing 30 days must stay within 85 to 95, and a breach fails the nightly job.
3. Threshold and bracket events from the first scorer: crossing probabilities at fixed
   thresholds and bracket probabilities where a market exists, scored with Brier and a
   reliability table. Point forecasts are scored on brackets through their own empirical
   error distribution from the record. The market-implied probability is a column.
4. Richer forecasters behind the same `Forecaster` protocol: neighbour networks as spatial
   features, model profiles, a state-space bias filter with ensemble spread and outlier
   rejection. The code is here; a network that is not public enters by configuration.
5. Observation impact as a scorecard row: any observation source added to a forecaster is
   scored with and without it, by lead. That is the only kind of assimilation claimed.

## Order of work

1. **Skeleton.** pyproject, CLAUDE.md, import contract, `localday` with its property test,
   CI, four ADRs, this plan, the feed table.
2. **Store and ingest.** Tables and migration; Postgres and in-memory stores under one read
   contract; feeds: Open-Meteo per model with profiles, NWS hourly grid, forecast
   discussion, IEM ASOS, IEM climate report, vendors, public market prices; heartbeat; the
   hourly job; the lookahead property test.
3. **Features and baselines.** Person-written tests first; daily extremes; running extreme;
   `Forecaster` protocol; raw-model and persistence baselines; `issue()`.
4. **Evaluate.** Settle, score, scorecard; golden backtest committed; the hourly cron on.
   Any wider station set is more rows in `data/stations.csv`, added when wanted.
5. **Serve and client.** Routes, OpenAPI types, the station map, the station page with
   scorecard, discussion and profile panes; the scorecard across stations.
6. **Public models and thresholds.** Consensus and the boosted model, with bands and the
   live coverage monitor; the first rows in `docs/EXPERIMENTS.md`.
7. **MCP server.** `forecast`, `observations`, `scorecard`, `profile`, `discussion`,
   `backtest`, all taking `as_of`; an agent runs the engines over these tools.
8. **More deep stations.** A column edit each; then the pooled model across them.

Targets after the high and low, in order: daily precipitation from the same climate
report, then hourly visibility and ceiling categories settled on METARs.
