# 0005. Market-implied probabilities are a public baseline; trading is not

Date: 2026-10-29
Status: accepted

## Context

Prediction markets on the daily high exist for a handful of cities and settle on the same
NWS climate report this service settles on. Their prices are a free, public, probabilistic
forecast that nobody has verified at station level. A verified record that leaves them out
would be incomplete at exactly the stations where readers can check it.

## Decision

Bracket prices from the public market API are sampled at every issue slot for the stations
that have a market and stored in `markets` with `received_at`. The market-implied
probability per bracket is a baseline column on the scorecard, scored with the Brier score
against the settled bracket alongside the NWS forecast and every forecaster that provides
quantiles. Only public market data enters: no keys, no accounts, no positions, no orders.
Anything that trades lives elsewhere and is not part of this repository.

Deep stations in the first set: Los Angeles, Miami, Chicago Midway, Austin and New York
Central Park, chosen for their different regimes (sea breeze on two coasts, the Midwest,
central Texas, the Northeast), plus Washington National for checks by eye. Each is a row.

## Consequences

The scorecard gains a bracket Brier row per forecaster. A point forecast is scored on
brackets through its own empirical error distribution from the record, so the NWS and the
raw models get a fair probabilistic score rather than a 0 or 1. A public reader can see,
per station and lead, whether the model, the NWS or the market was better calibrated.

## Alternatives rejected

- Keep markets out entirely: the record would be silent on the one public probabilistic
  forecast readers can trade against.
- Score point forecasts as 0/1 on brackets: punishes them for not being distributions.
