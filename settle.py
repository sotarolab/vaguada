"""Turn the archived climate reports into settlements: data/settlements/<station>.csv with one
row per report version. The preliminary report (valid as of 5 PM) and the final one (the next
morning) are both kept, each with the time it was issued and the time it was fetched, so a
score can say which it used and a backtest can see only what had arrived.

Run: python settle.py [out_dir]   (default: data/)
"""

from __future__ import annotations

import csv
import gzip
import sys
from datetime import UTC, datetime
from pathlib import Path

from vaguada import stations
from vaguada.parsers import iem_cli
from vaguada.parsers.schemas import c_to_f

COLUMNS = ["local_day", "target", "value_f", "final", "issued_at", "received_at"]


def stem_time(path: Path) -> datetime:
    return datetime.strptime(path.stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def settlements(out: Path, station: str) -> list[dict[str, object]]:
    """Every distinct (day, target, final, value) seen in the archive, with the first time it
    was fetched and the issue time of the product that carried it."""
    seen: dict[tuple[object, ...], dict[str, object]] = {}
    for p in sorted((out / "cli" / station).glob("*.gz")):
        received = stem_time(p)
        text = gzip.decompress(p.read_bytes()).decode(errors="replace")
        for product in iem_cli.split_products(text):
            issued = iem_cli.issued_at(product)
            if issued is None:
                continue
            for r in iem_cli.parse_one(product, station, received):
                value_f = round(c_to_f(float(r["value"])))
                key = (r["local_day"], r["target"], bool(r["final"]), value_f)
                if key not in seen:
                    seen[key] = {
                        "local_day": r["local_day"].isoformat(),
                        "target": r["target"],
                        "value_f": value_f,
                        "final": int(bool(r["final"])),
                        "issued_at": issued.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "received_at": received.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
    return sorted(seen.values(), key=lambda r: (str(r["local_day"]), str(r["target"]), str(r["issued_at"])))


def main(out: Path) -> int:
    (out / "settlements").mkdir(parents=True, exist_ok=True)
    total = 0
    for st in stations.load():
        if not (st["settles"] and st["settlement_source"] and (out / "cli" / st["station_id"]).is_dir()):
            continue
        rows = settlements(out, st["station_id"])
        with (out / "settlements" / f"{st['station_id']}.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, COLUMNS)
            w.writeheader()
            w.writerows(rows)
        total += len(rows)
    print(f"settled {total} report rows")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "data")))
