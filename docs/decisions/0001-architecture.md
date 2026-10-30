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

One station first, Los Angeles International, ingested deep: every model run hourly,
pressure-level profiles, the NWS hourly grid, the forecast discussion, vendor forecasts. A
station is a row in `stations`; adding one is data, not code.

The public repository is the instrument and the record: feeds, store, baselines, scoring,
routes, client. Forecasters beyond the baselines implement the public `Forecaster` protocol
from private packages and write to the same `predictions` table. Their scores are public;
their code is not.

## Consequences

Backtests and live runs share one function per forecaster. Lookahead is impossible by
construction and tested as a property. Early scorecards are thin, one station's rows, and
say so. The client is a port of an existing station page, with scorecard, discussion and
profile panes.

## Alternatives rejected

- Restructure the predecessor repository in place: its history and modules served a
  different product and would have coexisted with the new package under extra contracts.
- Many stations shallow: the breadth claim is available later by adding rows; depth at one
  station is what a forecaster needs on screen.
