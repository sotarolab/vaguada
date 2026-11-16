# Architecture

Four flat scripts, one package, one static page, one data branch. See `docs/PLAN.md` for
the order of work and `docs/decisions/` for why.

```
archive.py    fetch every live product for the stations due this hour; save as it arrived,
              gzipped, under data/<product>/<station>/<UTC fetch time>.gz; skip a file equal
              to the newest one already there
settle.py     every archived climate report -> data/settlements/<station>.csv, one row per
              report version (preliminary and final), with issue and fetch times
score.py      baselines at every local slot from files fetched before the slot (each raw
              model's daily extreme, the NWS daily series, persistence) and every model
              file under data/forecasts/, scored against the settlements
              -> data/scores/daily.csv
digest.py     data/site/index.json and data/site/stations/<station>.json: what the page draws
vaguada/      localday (local day, slots, lead), daily (daily and running extremes),
              parsers/ (one module per source: URL builder and parser), stations.csv
app/          Vite, React, Leaflet, uPlot; reads data/site from the data branch
```

Products and sources, checked 2026-10-29 and 2026-11-16:

| Product | Source | What is saved | When |
|---|---|---|---|
| openmeteo | Open-Meteo forecast API, five models in one call | hourly surface variables for 7 days; pressure-level profiles at deep stations | deep stations every hour, others at their local slots |
| nws_grid | api.weather.gov gridpoints | the raw grid: hourly temperature, daily max and min, and more, with the issue time | same |
| asos | IEM ASOS, one batched request | the last three hours of hourly METARs, split per station | same |
| cli | IEM AFOS `CLI<site>` | the last three climate report products | stations that settle |
| afd | IEM AFOS `AFD<office>` | the last two discussions | deep stations' offices |
| markets | public market API | the day's bracket markets with prices | stations with a market |
| nws_points | api.weather.gov points | the office and grid point, resolved once | first run |

Forecast contract for any model: `data/forecasts/<model>/<station>/<YYYY-MM-DDTHHZ>.csv`
with `date,target,lead_h,q05,q25,q50,q75,q95` in Fahrenheit; `target` is `tmax` or `tmin`;
the file stem is the issue instant. The ledger scores it beside the baselines and never
knows how it was made.

Point in time: filenames are fetch times. A baseline at slot `t` uses the newest file fetched
before `t`; persistence uses the settlement rows fetched before `t`. A backtest is the same
code over past slots.

Workflows: `archive.yml` runs the four scripts every hour and commits to the `data` branch;
`pages.yml` builds the page on pushes to `main` that touch `app/`; `tests.yml` runs ruff,
mypy and pytest on every push.
