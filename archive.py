"""Archive the live products at every station: the point models from Open-Meteo, the NWS
gridpoint forecast, the hourly observations, the NWS climate report, the area forecast
discussion and the public market brackets. Everything is saved as it arrived, gzipped, under
data/<product>/<station>/<UTC fetch time>.gz, and only when it differs from the newest file
already there. The fetch time in the name is the record of when it was known.

Run: python archive.py [out_dir]   (default: data/)
"""

from __future__ import annotations

import gzip
import json
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from vaguada import localday, stations
from vaguada.parsers import afd, iem_asos, iem_cli, markets, nws, open_meteo

USER_AGENT = "vaguada-archiver (github.com/sotarolab/vaguada)"


def fetch(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return bytes(r.read())
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"FAILED {url[:120]}: {e}", file=sys.stderr)
        return None


def save(out: Path, station: str, product: str, body: bytes, now: datetime) -> Path | None:
    """Write body gzipped under out/product/station/, unless it equals the newest file there."""
    d = out / product / station
    d.mkdir(parents=True, exist_ok=True)
    prev = sorted(d.glob("*.gz"))
    if prev and gzip.decompress(prev[-1].read_bytes()) == body:
        return None
    path = d / f"{now:%Y%m%dT%H%M%SZ}.gz"
    path.write_bytes(gzip.compress(body, mtime=0))  # mtime=0: same content gives the same bytes
    return path


def grid(out: Path, st: dict[str, Any]) -> tuple[str, int, int] | None:
    """The station's NWS office and grid point, resolved once and kept under data/nws_points."""
    path = out / "nws_points" / f"{st['station_id']}.json"
    if not path.exists():
        body = fetch(nws.points_url(st["lat"], st["lon"]))
        if body is None or body[:1] != b"{":
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    return nws.resolve_grid(json.loads(path.read_bytes()))


def due(st: dict[str, Any], now: datetime) -> bool:
    """Deep stations every hour; the others at their local slots."""
    return st["depth"] == "deep" or localday.slot_at(now, st["tz"]) is not None


def main(out: Path) -> int:
    now = datetime.now(UTC).replace(microsecond=0)
    active = [s for s in stations.load() if s["active"]]
    todo = [s for s in active if due(s, now.replace(minute=0, second=0))]
    saved = failed = tried = 0

    def take(station: str, product: str, url: str, ok: bool) -> None:
        nonlocal saved, failed, tried
        tried += 1
        body = fetch(url)
        if body is None or not ok or not body:
            failed += 1
            print(f"BAD PAYLOAD {station} {product}", file=sys.stderr)
            return
        saved += save(out, station, product, body, now) is not None

    # Observations: one request for every station due, the last three hours, split by station.
    if todo:
        body = fetch(iem_asos.url([s["station_id"] for s in todo], now - timedelta(hours=3), now))
        tried += 1
        if body is None or b"station,valid" not in body:
            failed += 1
            print("BAD PAYLOAD asos", file=sys.stderr)
        else:
            lines = body.decode().splitlines()
            header = next((ln for ln in lines if ln.startswith("station,")), "")
            for st in todo:
                mine = [ln for ln in lines if ln.startswith(iem_asos.iem_id(st["station_id"]) + ",")]
                if mine:
                    saved += (
                        save(out, st["station_id"], "asos", "\n".join([header, *mine]).encode() + b"\n", now)
                        is not None
                    )

    offices_done: set[str] = set()
    for st in todo:
        sid, deep = st["station_id"], st["depth"] == "deep"
        body = fetch(open_meteo.url(st["lat"], st["lon"], deep))
        tried += 1
        if body is None or b'"hourly"' not in body:
            failed += 1
            print(f"BAD PAYLOAD {sid} openmeteo", file=sys.stderr)
        else:
            # Strip the one field that changes on every call, so an unchanged forecast is not saved twice.
            payload = json.loads(body)
            payload.pop("generationtime_ms", None)
            saved += (
                save(out, sid, "openmeteo", json.dumps(payload, separators=(",", ":")).encode(), now)
                is not None
            )
        g = grid(out, st)
        if g:
            office, x, y = g
            body = fetch(nws.grid_url(office, x, y))
            tried += 1
            if body is None or b'"updateTime"' not in body:
                failed += 1
                print(f"BAD PAYLOAD {sid} nws_grid", file=sys.stderr)
            else:
                saved += save(out, sid, "nws_grid", body, now) is not None
            if deep and office not in offices_done:
                offices_done.add(office)
                b = fetch(afd.url(office))
                tried += 1
                if b and b"Area Forecast Discussion" in b:
                    saved += save(out, office, "afd", b, now) is not None
                else:
                    failed += 1
                    print(f"BAD PAYLOAD {office} afd", file=sys.stderr)
        if st["settles"] and st["settlement_source"]:
            b = fetch(iem_cli.url(st["settlement_source"]))
            tried += 1
            if b and b"CLIMATE" in b:
                saved += save(out, sid, "cli", b, now) is not None
            else:
                failed += 1
                print(f"BAD PAYLOAD {sid} cli", file=sys.stderr)
        if st["market_series"]:
            b = fetch(markets.url(st["market_series"]))
            tried += 1
            if b and b[:1] == b"{":
                saved += save(out, sid, "markets", b, now) is not None
            else:
                failed += 1
                print(f"BAD PAYLOAD {sid} markets", file=sys.stderr)

    print(f"{now:%Y-%m-%dT%H:%MZ} {len(todo)} stations due; saved {saved} new, {failed} failed, of {tried}")
    return 1 if tried and failed > tried // 2 else 0  # loud only when the sources are broadly down


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "data")))
