# 0001. A point-in-time forecasting service, one station first

Date: 2026-10-29
Status: accepted

## Context

A predecessor project corrected hourly temperature for 165 stations at render time in a
single web app, with no stored predictions and bands that claimed 95% and covered about
80%. Nobody decides on hourly temperature; the daily high and low are what people act on
and the only quantity with an official number, the NWS climate report. Published forecast
comparisons routinely grade sources against the last snapshot of the day, after the high
has occurred, and have had to be retracted for it.

## Decision

A layered package, dependencies pointing down only, enforced by import-linter in CI:
`serve > evaluate > forecast > features | ingest > store > localday | config`.

Every stored row has `valid_at` and `received_at`; every read takes `as_of`. A prediction
is written at its issue slot and never changed. Scheduled jobs write tables; routes read
tables; the client computes nothing. Feeds never raise.

Stations are rows in `data/stations.csv` with a depth column. Slot depth means the latest
run per model per slot, the NWS grid, hourly observations and the climate report where one
exists. Deep means every model run hourly, pressure-level profiles, the forecast
discussion, vendor forecasts and the corrected forecasters. The first set is Los Angeles
International, deep, and the thirteen other ASOS stations of the Los Angeles basin at slot
depth, which are the public neighbour ring. A wider set is more rows.

All code is public: feeds, store, baselines, models, scoring, routes, client. Every
forecaster implements one `Forecaster` protocol and writes to the same `predictions`
table. What stays outside the repository is data and credentials: a station network that
is not public enters by configuration, and nothing that trades is part of this project.

## Consequences

Backtests and live runs share one function per forecaster. Lookahead is impossible by
construction and tested as a property. Early scorecards are thin on days, if not on stations, and
say so. The client is a port of an existing station page, with scorecard, discussion and
profile panes.

## Alternatives rejected

- Restructure the predecessor repository in place: its history and modules served a
  different product and would have coexisted with the new package under extra contracts.
- One station only: the spatial stage and the map need neighbours from day one.
- Every ASOS station in the network: cheap at slot depth, but a decision that can be made
  later by adding rows, and nothing in the first months needs it.
