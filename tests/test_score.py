"""Claims about scoring, on a synthetic archive in a temp directory.

1. A baseline at slot t is built only from files fetched before t, and scored against the
   settled value of the day it targets, at the lead from t to the end of that local day.
2. A model forecast file is scored by the CRPS of its quantiles and whether the outcome fell
   inside q05 to q95; a point baseline's CRPS is its absolute error.
3. A final climate report wins over a preliminary one for the same day.
"""

import gzip
import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import score
import settle
from vaguada import localday

TZ = "America/Los_Angeles"
SID = "asos:KLAX"
ST = {"station_id": SID, "tz": TZ, "settles": True, "depth": "deep", "lat": 33.9, "lon": -118.4}
DAY = date(2026, 7, 15)


def stamp(t: datetime) -> str:
    return t.strftime("%Y%m%dT%H%M%SZ")


def write_gz(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = payload if isinstance(payload, str) else json.dumps(payload)
    path.write_bytes(gzip.compress(body.encode(), mtime=0))


def openmeteo_payload(start: datetime, hours: int, base_c: float) -> dict:
    """A diurnal cycle peaking at 22 UTC (15:00 PDT): base + 10 at the peak, base at dawn."""
    times, temps = [], []
    for i in range(hours):
        t = start + timedelta(hours=i)
        times.append(t.strftime("%Y-%m-%dT%H:%M"))
        temps.append(base_c + 5 + 5 * math.cos(((t.hour - 22) % 24) / 24 * 2 * math.pi))
    return {"hourly": {"time": times, "temperature_2m_gfs_global": temps}}


def nws_payload(update: datetime, days: list[tuple[date, float, float]]) -> dict:
    """maxTemperature from 14Z (07 local), minTemperature from 03Z the evening before."""
    mx = [{"validTime": f"{d.isoformat()}T14:00:00+00:00/PT13H", "value": hi} for d, hi, _ in days]
    mn = [{"validTime": f"{d.isoformat()}T03:00:00+00:00/PT14H", "value": lo} for d, _, lo in days]
    hour = f"{update:%Y-%m-%dT%H}:00:00+00:00/PT1H"
    return {
        "properties": {
            "updateTime": update.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "temperature": {"uom": "wmoUnit:degC", "values": [{"validTime": hour, "value": 20.0}]},
            "maxTemperature": {"uom": "wmoUnit:degC", "values": mx},
            "minTemperature": {"uom": "wmoUnit:degC", "values": mn},
        }
    }


def test_baselines_and_model_file_are_scored(tmp_path: Path) -> None:
    out = tmp_path
    yday = DAY - timedelta(days=1)
    # Settlements: yesterday 70 F (preliminary early, final later); the day 75 F high (a
    # preliminary 74 first), 60 F low.
    settle_dir = out / "settlements"
    settle_dir.mkdir()
    (settle_dir / f"{SID}.csv").write_text(
        "local_day,target,value_f,final,issued_at,received_at\n"
        f"{yday - timedelta(days=1)},tmax,66,1,2026-07-14T09:40:00Z,2026-07-14T10:00:00Z\n"
        f"{yday},tmax,70,0,2026-07-15T00:30:00Z,2026-07-15T01:00:00Z\n"
        f"{yday},tmax,70,1,2026-07-15T09:40:00Z,2026-07-15T10:00:00Z\n"
        f"{DAY},tmax,74,0,2026-07-16T00:30:00Z,2026-07-16T01:00:00Z\n"
        f"{DAY},tmax,75,1,2026-07-16T09:40:00Z,2026-07-16T10:00:00Z\n"
        f"{DAY},tmin,60,1,2026-07-16T09:40:00Z,2026-07-16T10:00:00Z\n"
    )
    # One Open-Meteo file and one NWS grid, both fetched the evening before at 18:30 local, so
    # the 18:00 slot that evening cannot see them but the 00:00 slot can.
    slot18 = localday.slot_time(yday, 18, TZ)
    fetched = slot18 + timedelta(minutes=30)
    write_gz(
        out / "openmeteo" / SID / f"{stamp(fetched)}.gz",
        openmeteo_payload(fetched.replace(minute=0), 72, 18.0),
    )
    nws_days = [(DAY, 24.0, 15.0), (DAY + timedelta(days=1), 25.0, 16.0)]
    write_gz(out / "nws_grid" / SID / f"{stamp(fetched)}.gz", nws_payload(fetched, nws_days))
    # A model file issued at the 00:00 slot of the day.
    slot0 = localday.slot_time(DAY, 0, TZ)
    f = out / "forecasts" / "tmax_v1" / SID / f"{slot0:%Y-%m-%dT%HZ}.csv"
    f.parent.mkdir(parents=True)
    f.write_text(
        "date,target,lead_h,q05,q25,q50,q75,q95\n"
        f"{DAY},tmax,24,71,73,74,76,78\n"
        f"{DAY},tmin,24,55,58,60,62,64\n"
    )

    rows = score.score_station(out, ST, datetime(2026, 7, 17, tzinfo=UTC))
    by = {(r["product"], r["issue"], r["target"]): r for r in rows}
    k18 = slot18.strftime("%Y-%m-%dT%H:%M:%SZ")
    k0 = slot0.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Nothing from the models at the 18:00 slot (their files arrived after it); rows from 00:00.
    assert not any(r["issue"] == k18 and r["product"] in ("raw_gfs", "nws") for r in rows)
    nws_row = by[("nws", k0, "tmax")]
    assert nws_row["obs_f"] == 75 and nws_row["report"] == "final"  # 3. final beats preliminary
    assert nws_row["q50"] == round(24.0 * 9 / 5 + 32, 1) and nws_row["crps"] == round(abs(75.2 - 75), 2)
    assert nws_row["lead_h"] == 24.0
    assert by[("raw_gfs", k0, "tmax")]["lead_h"] == 24.0
    # Persistence at 00:00: the most recent settled high as known then, yesterday's preliminary
    # (its final came later), not the older day's final.
    assert by[("persistence", k0, "tmax")]["q50"] == 70.0
    assert by[("persistence", k0, "tmax")]["crps"] == 5.0
    # 2. The model file: CRPS of its quantiles, the coverage flag, the lead from the file.
    m = by[("tmax_v1", k0, "tmax")]
    assert m["crps"] == round(score.crps([71, 73, 74, 76, 78], 75), 2)
    assert m["in90"] == 1 and m["lead_h"] == 24.0
    assert by[("tmax_v1", k0, "tmin")]["in90"] == 1


def test_settlements_keep_both_report_versions(tmp_path: Path) -> None:
    prelim = "\n".join(
        [
            "CDUS46 KLOX 160030",
            "CLILAX",
            "",
            "CLIMATE REPORT",
            "NATIONAL WEATHER SERVICE LOS ANGELES/OXNARD CA",
            "530 PM PDT WED JUL 15 2026",
            "",
            "...THE LOS ANGELES INTL AIRPORT CA CLIMATE SUMMARY FOR JULY 15 2026...",
            "VALID TODAY AS OF 0500 PM LOCAL TIME.",
            "",
            "TEMPERATURE (F)",
            "  TODAY",
            "   MAXIMUM         74    219 PM  84    1950  60      6       61",
            "   MINIMUM         60    605 AM  -2    1917  32      5       21",
            "",
            "PRECIPITATION (IN)",
            "",
        ]
    )
    final = (
        prelim.replace("530 PM PDT WED JUL 15 2026", "240 AM PDT THU JUL 16 2026")
        .replace("VALID TODAY AS OF 0500 PM LOCAL TIME.", "VALID AS OF MIDNIGHT LOCAL TIME.")
        .replace("MAXIMUM         74", "MAXIMUM         75")
    )
    d = tmp_path / "cli" / SID
    d.mkdir(parents=True)
    (d / "20260716T010000Z.gz").write_bytes(gzip.compress(("\x01" + prelim).encode(), mtime=0))
    (d / "20260716T100000Z.gz").write_bytes(
        gzip.compress(("\x01" + prelim + "\x01" + final).encode(), mtime=0)
    )
    rows = settle.settlements(tmp_path, SID)
    highs = [(r["value_f"], r["final"], r["received_at"]) for r in rows if r["target"] == "tmax"]
    assert highs == [(74, 0, "2026-07-16T01:00:00Z"), (75, 1, "2026-07-16T10:00:00Z")]
    assert [r["value_f"] for r in rows if r["target"] == "tmin"] == [60, 60]
