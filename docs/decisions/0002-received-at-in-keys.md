# 0002. Key observations and settlements by received_at

Date: 2026-10-29
Status: accepted

## Context

The NWS climate report is issued twice: a preliminary product around 5 PM local that says
"valid today as of 5 PM", and a final product the next morning for the full day. ASOS
observations are also revised. A table keyed on station, day and target can hold only one
of those values, so storing the correction means overwriting history, and a backtest would
then see the final value as if it had been known at 5 PM.

## Decision

`received_at` is part of the primary key of `observations` and `settlements`. A correction
is a new row. A read at `as_of` returns, per key, the row with the latest `received_at`
that is `<= as_of`. `scores` and `scorecard` are derived tables and the only ones rebuilt
in place. `stations` is edited by hand. Every other table is append-only.

## Consequences

Reads use `DISTINCT ON` and are slightly more expensive. A re-fetch that returns the same
value adds no row; only a changed value is a correction, so the hourly job can re-read a
window of recent hours without growing the table. A day can be settled
provisionally at the preliminary report and re-scored at the final one, and the scorecard
can show both. The lookahead property test covers corrections directly.

## Alternatives rejected

- A separate corrections table: two places to read on every query.
- Overwrite in place: the point-in-time claim becomes false for the one table the
  scorecard rests on.
