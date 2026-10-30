# 0003. Fixed local issue slots; lead is hours to the end of the local day

Date: 2026-10-29
Status: accepted

## Context

A daily high has no natural instant to measure lead from, and models arrive on their own
cadences, from four runs a day to hourly. Issuing a prediction on every model run ties the
scorecard to the busiest model and produces many near-identical training rows per day.

## Decision

Predictions are issued at fixed local slots: 00:00, 06:00, 12:00 and 18:00. Each target is
scored at the six slots before its typical time: the high at day-ahead 06, 12, 18 and
same-day 00, 06, 12; the low at 18:00 two days before, then 00, 06, 12, 18 the day before
and 00:00 on the day. The 18:00 slot also issues days 2 through 5 for both targets.

`lead_h` is the hours from the slot to the end of the target's local day. The scorecard
displays by slot name and days ahead. Baselines are sampled at the same slots through the
point-in-time read, so every column saw the same information. One training sample per
station, day and slot, with lead as a feature.

All of this lives in `stationcast.localday` and nowhere else, with a property test across
every station time zone and the DST transitions of 2025 to 2027.

## Consequences

The hourly job asks each station whether the current hour is one of its slots, so one
cron serves every time zone. The same-day slots carry the running observed extreme as a
feature and are the nowcast leads on the scorecard.

## Alternatives rejected

- Lead to the start of the day: same-day forecasts get negative leads.
- Issue per model run: scorecard and training tied to run cadence.
- Score by fixed NWS issue times only: raw models do not run on those slots.
