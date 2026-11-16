# Plan

Rewritten 2026-11-16. A public ledger of station daily high and low forecasts, scored every
day against the NWS climate report, in the same shape as the river ledger that preceded it:
flat scripts, a data branch, a static page, and models in their own packages.

## Decisions

| Question | Decision | Record |
|---|---|---|
| Shape | A ledger on a data branch; no database, no service | 0007 |
| Keys | Filenames are fetch times; nothing is revised; both climate report versions kept | 0002, 0007 |
| Issue cadence | Local slots 00/06/12/18 for baselines; lead to the end of the local day | 0003 |
| Models | Separate packages writing one CSV of quantiles per station and issue | 0007 |
| Stations | Rows in `vaguada/stations.csv`; six deep stations and the Los Angeles basin ring | 0001 |
| Markets | Archived as public prices; scored as a column later; nothing trades | 0005 |
| Learning | A journal and a day summary, once the record has days to summarise | 0006 |

## Order of work

1. **Ledger.** The four scripts, the package, the tests, the hourly workflow, the data
   branch. Done 2026-11-16.
2. **Page.** The river ledger's app adapted: station picker, chart with observed, every
   model, the NWS and the model fans, scorecards by lead and station, radar on the map,
   the discussion.
3. **Model.** The temperature package: train on the reforecast archive and the climate
   reports, issue twice a day for the deep stations into `data/forecasts/`. The first
   scored rows the next morning.
4. **Then:** climatology baseline from NCEI normals; pre-registered events as a CSV and a
   scorecard filter; the journal as markdown under `data/journal/`; neighbour observations
   from the public CWOP network through MADIS and a nowcast model issuing hourly through
   the same contract.
