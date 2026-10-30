# 0006. Every day leaves a record a person and a model can learn from

Date: 2026-10-30
Status: accepted

## Context

A forecaster's edge at a station is knowing which model to trust under which conditions:
the marine layer, offshore flow, a front timed wrong, a sea breeze that arrives early. That
knowledge accumulates day by day and is lost unless each day is written down with its
conditions and its outcome. A scorecard by lead cannot answer "what happened last time it
looked like this".

## Decision

Two tables and one read.

`journal` is append-only, written by a person through the page: per station and local day,
an uncertainty rating, regime tags, and free text, with `created_at`. It is the one write
route in the service.

`day_summary` is derived, rebuilt by the nightly scorer: per station and local day, the
settled high and low, each baseline's and each forecaster's error, the spread across the
raw models at each slot, the market-implied error where a market exists, and regime
features computed in `features/` from the stored profiles and observations: inversion base
and strength, 850 hPa temperature, low-level wind speed and direction, cloud cover, and
the season as the day of year.

`analogs(station, day, k)` reads the nearest past days in `day_summary` by regime features
and season and returns them with their errors. It is a pane on the page and a tool for the
assistant, which can then flag a forecast with "on the twelve closest days the NBM ran
warm by 3 F and the market was off by two brackets".

## Consequences

The scorer gains a second derived table. `features/` gains regime functions, read line by
line like the rest of it. The journal is the only table the page writes to, and it has no
effect on any forecast until a forecaster chooses to read it.

## Alternatives rejected

- Notes in a spreadsheet: not joined to the record, not readable by a tool.
- Features only, no journal: the person's reading of the day is the part no feed carries.
