# camanchaca-demo

A station-level forecasting service for the daily high and low. Every forecast is stored
before settlement and scored nightly against the official climate report, the raw models,
the NWS forecast and a vendor. One station first; a station is a row, never a branch.
The plan is `docs/PLAN.md`; decisions are in `docs/decisions/`; the layout and the feed
table are in `docs/ARCHITECTURE.md`.

## Rules

- **Point in time, always.** Every stored row has `valid_at` and `received_at`, UTC,
  tz-aware. Every read takes `as_of` and returns rows with `received_at <= as_of`. A
  correction is a new row. Local day is derived in `camanchaca_demo.localday` and nowhere else.
- **One path.** The function that forecasts today at a slot is the function the backtest
  calls for a slot last month.
- **Nothing computes at request time.** Jobs write tables; routes read tables.
- **The client computes nothing.** Numbers come from Python with tests.
- **Frames have schemas.** pandera at every boundary that passes a DataFrame.
- **Feeds never raise.** Empty typed frame on failure, heartbeat row written.
- **A feature ships only with a line on the scorecard.**
- **Science is read by a person.** `features/` and `forecast/` stay small; their tests are
  written first, by a person, as the claim the code must meet. Every forecaster implements
  the `Forecaster` protocol. All code is public; private inputs enter by configuration.
- **Numbers exist only as CI output.** A metric is a row in `docs/EXPERIMENTS.md` with its
  commit, or it is not a result.
- **ADRs at decision time**, one page, dated, in `docs/decisions/`.
- **Plain prose in the repo**: no em dashes, no hedging, no claims without a number behind
  them. Keys, credentials and non-public data never enter the repository.

## Commands

```bash
pip install -e ".[dev,service]"      # one install
ruff check . && mypy -p camanchaca_demo && lint-imports
pytest -v
alembic upgrade head                  # needs DATABASE_URL
python scripts/ingest.py --now        # the hourly job; --slot and --stations for one run
python scripts/score.py               # settle closed days, score, rebuild the scorecard
uvicorn camanchaca_demo.serve.app:app --reload
```

## Skills

`/review` walks a plan review queue one item per turn. `/adr` records a decision.

## Process

Small PRs, one layer each. Plan mode for multi-layer changes. The code-review skill runs
before a person reads a PR. The person merges.
