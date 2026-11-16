# vaguada

A public, timestamped record of daily high and low temperature forecasts at weather
stations, scored against the NWS climate report.

Every hour a workflow archives the live products exactly as they arrived: five point
models from Open-Meteo (GFS, HRRR, NBM, ECMWF IFS, ICON) with pressure-level profiles at
the deep stations, the NWS gridpoint forecast, the hourly observations, the climate report,
the area forecast discussion, and the public market brackets where a market exists. The
files are named by the time they were fetched and are never revised. Once a day's climate
report is in, every forecast of that day is scored at the lead it was issued at: each raw
model's daily extreme, the NWS, persistence, and any model that wrote a forecast file.

Models are separate packages. A model writes
`data/forecasts/<model>/<station>/<issue>.csv` with `date,target,lead_h,q05,q25,q50,q75,q95`
in Fahrenheit, and the ledger scores it like any other product.

The first stations are Los Angeles International, followed in depth, with the other ASOS
stations of the Los Angeles basin around it, and Miami, Chicago Midway, Austin, New York
Central Park and Washington National. A station is a row in `vaguada/stations.csv`.

```
python archive.py data     # data/<product>/<station>/<UTC time>.gz, skipping unchanged files
python settle.py data      # data/settlements/<station>.csv from the archived climate reports
python score.py data       # data/scores/daily.csv, one row per forecast, target and day
python digest.py data      # data/site/, what the page draws
python -m pytest tests
```

The archive, settlements and scores live on the `data` branch. A static page that reads
that branch is the next change.

## How this is built

The code is written with an AI assistant under gates that run in CI on every change: a
lint pass, strict typing, unit tests with saved responses from every source, and a scorer
test on a synthetic archive. Decisions are recorded the day they are made in
`docs/decisions/`. A metric is a result only as a row in the scores file with the commit
that produced it.

## License

MIT.
