# vaguada

A public ledger of station daily high and low forecasts. Every hour a workflow archives the
live products as they arrived, settles the days the NWS climate report has closed, scores
every forecast and every baseline, and writes the data the static page draws. Models live
in their own packages and write one CSV per station and issue into the ledger. The plan is
`docs/PLAN.md`; decisions are in `docs/decisions/`; the layout and feeds in
`docs/ARCHITECTURE.md`.

## Rules

- **Nothing is revised.** A product is saved as it arrived, named by its fetch time. A
  forecast file is never rewritten. The fetch time is the record of what was known.
- **Scores use only what had arrived.** A baseline at slot `t` is built from files fetched
  before `t`; a model file is scored as issued. A backtest is the same code over past hours.
- **The ledger never knows how a model works.** It reads
  `forecasts/<model>/<station>/<issue>.csv` and scores it beside the baselines.
- **The page computes nothing.** `digest.py` writes every number, label and unit.
- **Local day is derived in `vaguada/localday.py` and nowhere else.**
- **Numbers exist only as rows** in `data/scores/daily.csv` on the data branch, and in
  `docs/EXPERIMENTS.md` with the commit that produced them.
- **Plain prose in the repo**: no em dashes, no hedging, no claims without a number behind
  them. Keys, credentials and non-public data never enter the repository.

## Commands

```bash
pip install -e ".[dev]"
ruff check . && mypy -p vaguada && mypy archive.py settle.py score.py digest.py && pytest -q
python archive.py data && python settle.py data && python score.py data && python digest.py data
```

## Process

Small PRs, one layer each. Plan mode for multi-layer changes. The code-review skill runs
before a person reads a PR. The person merges. ADRs at decision time.
