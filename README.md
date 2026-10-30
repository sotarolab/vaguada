# stationcast

A station-level forecasting service for the daily high and low. Every forecast is stored
before the day settles and scored every night against the official climate report, the raw
models, the NWS forecast and a vendor. The first station is Los Angeles International.

Status: day one. There is a plan, a set of decisions, a local-day module with its tests and
the gates that every later change passes. Nothing forecasts yet.

- Plan: `docs/PLAN.md`
- Decisions: `docs/decisions/`
- Layout and feeds: `docs/ARCHITECTURE.md`

## How this is built

The code is written with an AI assistant under gates that run in CI on every change: a lint
pass, strict typing, an import contract that keeps the layers one-directional, unit and
property tests, and a committed golden backtest once the scorer exists. Decisions are
recorded the day they are made. The science modules are small enough to be read line by
line, and their tests are written first by a person. A metric is a result only when it is a
row in `docs/EXPERIMENTS.md` with the commit that produced it.

## License

MIT.
