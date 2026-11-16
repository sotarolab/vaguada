"""The digest's shape on an empty archive and on a scored file."""

from datetime import UTC, datetime
from pathlib import Path

import digest


def test_index_on_empty_archive(tmp_path: Path) -> None:
    idx = digest.build(tmp_path, datetime(2026, 7, 17, tzinfo=UTC))
    assert idx["record_start"] is None and idx["archive_days"] == 0
    assert len(idx["stations"]) == 19 and idx["scores"] == {"by_lead": [], "by_station": []}
    assert (tmp_path / "site" / "stations" / "asos:KLAX.json").exists()


def test_scorecards_group_by_bucket(tmp_path: Path) -> None:
    d = tmp_path / "scores"
    d.mkdir()
    (d / "daily.csv").write_text(
        "product,station,issue,target,date,lead_h,obs_f,q50,crps,in90,report\n"
        "nws,asos:KLAX,2026-07-15T07:00:00Z,tmax,2026-07-15,24.0,75,74,1.0,,final\n"
        "nws,asos:KLAX,2026-07-15T13:00:00Z,tmax,2026-07-15,18.0,75,76,1.0,,final\n"
        "tmax_v1,asos:KLAX,2026-07-15T07:00:00Z,tmax,2026-07-15,24.0,75,74,0.8,1,final\n"
    )
    cards = digest.scorecards(tmp_path)
    by_lead = {(c["product"], c["lead"]): c for c in cards["by_lead"]}
    assert by_lead[("nws", "12-24")]["n"] == 1 and by_lead[("nws", "24-48")]["n"] == 1
    assert by_lead[("tmax_v1", "24-48")]["cov90"] == 1.0 and by_lead[("nws", "24-48")]["cov90"] is None
    assert by_lead[("nws", "12-24")]["bias"] == 1.0 and by_lead[("nws", "24-48")]["thin"] is True
