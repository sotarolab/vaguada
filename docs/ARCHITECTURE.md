# Architecture

See `docs/PLAN.md` for the layout and the database, and `docs/decisions/` for why.

## Dependency direction

```
serve  >  evaluate  >  forecast  >  features | ingest  >  store  >  localday | config
```

A layer imports only the layers below it. `features` imports pandas and `localday` only.
`.importlinter` runs in CI.

## Feeds

Checked 2026-10-29 at KDEN and KLAX with one request per source. Horizon counts are hours
of non-null `temperature_2m` in a 7-day request.

| Feed | Source | Variables | Horizon | Cadence | Notes |
|---|---|---|---|---|---|
| GFS | Open-Meteo `gfs_global` | t2m, td2m, cloud, precip, visibility; profiles at 1000/925/850/700/500 hPa (T, Z, wind, RH); boundary layer height | 168 h | 4 runs/day | Cycle not reported; `run_at` is the fetch hour |
| HRRR | Open-Meteo `gfs_hrrr` | same, profiles included | 49 h | hourly runs | 48 h only at 00/06/12/18 UTC cycles |
| NBM | Open-Meteo `ncep_nbm_conus` | t2m, td2m, cloud, precip; visibility partial | 168 h | hourly runs | No profiles, no boundary layer height |
| ECMWF IFS | Open-Meteo `ecmwf_ifs025` | t2m, td2m, cloud, precip; profiles | 168 h | 2 to 4 runs/day | No visibility, no boundary layer height |
| ICON | Open-Meteo `icon_global` | t2m, td2m, cloud, precip; profiles | 168 h | 4 runs/day | No visibility, no boundary layer height |
| NWS grid | api.weather.gov `gridpoints/{office}/{x},{y}` | hourly temperature, dewpoint, maxTemperature, minTemperature, sky cover, wind, PoP, QPF, hazards and more, each with its own valid-time runs | 7 d 8 h | updates several times a day | `updateTime` is the issue time; this is the settlement-grade NWS forecast |
| NWS hourly | api.weather.gov `.../forecast/hourly` | temperature, wind, PoP per hour | 156 h | per update | Derived from the grid |
| NWS periods | api.weather.gov `.../forecast` | day/night temperature | 14 periods | per update | Day high, night low |
| Discussion | IEM AFOS `pil=AFD{office}` | text with issue time | n/a | 2 to 4 per day plus updates | Office LOX for KLAX |
| Observations | IEM ASOS `asos.py`, `report_type=3` | tmpf, dwpf, sky, visibility, precip, wind, pressure, wx codes | n/a | hourly METAR | Request in UTC |
| Settlement | IEM AFOS `pil=CLI{site}` | daily max, min, times, normals, records | n/a | preliminary ~5 PM local, final next morning | Both versions stored; `received_at` separates them |
| Markets | public market API, `markets?series_ticker=KXHIGH{city}&status=open` | bracket strikes, yes bid/ask, last price, close time | the day's markets | sampled at slots | No key needed; prices only |
| Vendors | daily high/low per point from vendor APIs with free tiers | tmax, tmin per day | 5 to 15 d | per fetch | One adapter each; absent when the key is missing; within each free limit |

## Jobs

- `scripts/ingest.py --now`: every hour. Floors the clock to the hour, asks each active
  station whether it is a slot, fetches every feed for that station, writes rows with
  `received_at = now`, then issues predictions for the slot's targets.
- `scripts/score.py`: after ingest. Settles closed days from the climate report, scores
  predictions against settlements, rebuilds `scores` and `scorecard`.
- Both run from `.github/workflows/slots.yml` with the database URL as a repository secret,
  and locally with the same commands.

## Service and page

`camanchaca_demo.serve.app` is FastAPI. Routes read tables: `/healthz` (per-feed heartbeat),
`/api/stations`, `/api/station/{id}` (the whole station page in one response, temperatures
in Fahrenheit, time series as columnar arrays), `/api/journal/{id}` and `POST /api/journal`,
the one write route (decision 0006). The client is Vite, React and uPlot under `client/`;
its API types are generated from the service's OpenAPI schema and CI fails on a stale copy.
The built page is served by the service at `/`.
