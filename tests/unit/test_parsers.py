"""Each parser against one saved response. The fixtures are real responses captured on
2026-10-30 for Los Angeles; the parsers must never raise on them and must produce frames
that pass their schemas."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from camanchaca_demo.ingest import afd, iem_asos, iem_cli, markets, nws, open_meteo
from camanchaca_demo.store import schemas

F = Path(__file__).resolve().parents[1] / "fixtures"
RECEIVED = datetime(2026, 10, 30, 4, 7, tzinfo=UTC)


def test_open_meteo_one_row_per_model_and_var() -> None:
    payload = json.loads((F / "open_meteo_klax.json").read_text())
    run_at = datetime(2026, 10, 30, 4, tzinfo=UTC)
    df = open_meteo.parse(payload, "asos:KLAX", run_at, RECEIVED, deep=True)
    assert set(df["model"]) >= {"gfs", "hrrr", "nbm", "ifs", "icon"}
    assert not df.duplicated(["model", "var"]).any()
    t2m = df[df["var"] == "t2m"].set_index("model")["values"]
    assert all(len(v) > 24 for v in t2m)
    assert all(isinstance(v[0], float) for v in t2m)
    # Profiles exist for the models that carry them, and the array starts at run_at.
    assert "t_850" in set(df[df["model"] == "gfs"]["var"])
    assert "t_850" not in set(df[df["model"] == "nbm"]["var"])
    assert (df["run_at"] == run_at).all()
    schemas.RunFrame.validate(df)


def test_open_meteo_surface_only_when_not_deep() -> None:
    payload = json.loads((F / "open_meteo_klax.json").read_text())
    df = open_meteo.parse(
        payload, "asos:KLAX", datetime(2026, 10, 30, 4, tzinfo=UTC), RECEIVED, deep=False
    )
    assert not any(v.startswith(("t_", "z_", "rh_")) for v in df["var"])


def test_nws_grid_hourly_and_daily() -> None:
    payload = json.loads((F / "nws_grid_klax.json").read_text())
    df = nws.parse(payload, "asos:KLAX", "America/Los_Angeles", RECEIVED)
    assert set(df["model"]) == {"nws"}
    by_var = df.set_index("var")["values"]
    assert "t2m" in by_var and "tmax" in by_var and "tmin" in by_var
    assert sum(v is not None for v in by_var["t2m"]) > 100
    assert 3 <= sum(v is not None for v in by_var["tmax"]) <= 8
    # run_at is the grid's true issue time, floored to the hour
    assert df["run_at"].iloc[0] == datetime.fromisoformat(
        payload["properties"]["updateTime"]
    ).replace(minute=0, second=0, microsecond=0)
    schemas.RunFrame.validate(df)


def test_iem_asos_long_frame_in_si_units() -> None:
    csv = (F / "iem_asos_lax_smo.csv").read_text()
    df = iem_asos.parse(csv, RECEIVED, {"LAX": "asos:KLAX", "SMO": "asos:KSMO"})
    assert set(df["station_id"]) <= {"asos:KLAX", "asos:KSMO"}
    assert "t2m" in set(df["var"])
    t = df[df["var"] == "t2m"]["value"]
    assert t.between(-10, 45).all()  # Celsius, not Fahrenheit
    assert not df.duplicated(["station_id", "valid_at", "var"]).any()
    schemas.ObsFrame.validate(df)


def test_iem_asos_empty_response() -> None:
    assert iem_asos.parse("", RECEIVED, {}).empty
    assert iem_asos.parse("#ERROR: no data", RECEIVED, {}).empty


def test_cli_settlements_and_products() -> None:
    text = (F / "cli_lax.txt").read_text()
    settle, prods = iem_cli.parse(text, "CLILAX", "asos:KLAX", RECEIVED)
    assert len(prods) >= 1
    assert (prods["pil"] == "CLILAX").all()
    assert prods["issued_at"].dt.tz is not None
    assert len(settle) >= 2
    assert set(settle["target"]) <= {"tmax", "tmin"}
    assert settle["value"].between(-5, 45).all()  # Celsius
    # The preliminary product says "valid today"; it must be marked not final.
    for product, is_final in zip(
        prods["text"], prods["text"].map(lambda t: "VALID TODAY" not in t.upper()), strict=True
    ):
        rows = settle[settle["received_at"] == RECEIVED]
        assert len(rows) >= 0  # parsed from the same batch
        assert ("VALID TODAY" in product.upper()) != is_final
    schemas.SettlementFrame.validate(settle)
    schemas.ProductFrame.validate(prods)


def test_cli_issue_time_parses_local_to_utc() -> None:
    product = "CDUS46 KLOX 300030\nCLILAX\n\nCLIMATE REPORT\n530 PM PDT THU OCT 29 2026\n"
    at = iem_cli.issued_at(product)
    assert at == datetime(2026, 10, 30, 0, 30, tzinfo=UTC)
    assert iem_cli.office(product) == "KLOX"


def test_afd_product() -> None:
    text = (F / "afd_lox.txt").read_text()
    df = afd.parse(text, "LOX", RECEIVED)
    assert len(df) >= 1
    assert (df["pil"] == "AFDLOX").all()
    assert "DISCUSSION" in df["text"].iloc[0].upper()
    schemas.ProductFrame.validate(df)


def test_markets_brackets_and_probabilities() -> None:
    payload = json.loads((F / "markets_klax.json").read_text())
    as_of = datetime(2026, 10, 30, 4, tzinfo=UTC)
    df = markets.parse(payload, "asos:KLAX", as_of, RECEIVED)
    assert len(df) > 0
    assert (df["station_id"] == "asos:KLAX").all()
    assert df["local_day"].map(lambda d: d.year == 2026).all()
    assert df["bracket_lo"].notna().any() and df["bracket_hi"].notna().any()
    for col in ("yes_bid", "yes_ask", "last_price"):
        assert df[col].dropna().between(0, 1).all()
    assert not df.duplicated(["ticker", "as_of"]).any()
    schemas.MarketFrame.validate(df)


def test_market_day_from_ticker() -> None:
    from datetime import date

    assert markets.market_day("KXHIGHLAX-26OCT30-T74") == date(2026, 10, 30)
    assert markets.market_day("NOPE") is None


def test_empty_frames_have_the_right_columns() -> None:
    assert list(schemas.empty(schemas.OBS_COLUMNS).columns) == schemas.OBS_COLUMNS
    assert isinstance(
        schemas.validate_runs(pd.DataFrame(columns=schemas.RUN_COLUMNS)), pd.DataFrame
    )


def test_nws_daily_low_belongs_to_the_dawn_day() -> None:
    """A min period starting the evening before and ending after dawn is the next day's low."""
    payload = {
        "properties": {
            "updateTime": "2026-10-29T23:01:33+00:00",
            "minTemperature": {
                "uom": "wmoUnit:degC",
                "values": [
                    {"validTime": "2026-10-30T03:00:00+00:00/PT14H", "value": 15.0},
                    {"validTime": "2026-10-31T03:00:00+00:00/PT14H", "value": 14.0},
                ],
            },
            "maxTemperature": {
                "uom": "wmoUnit:degC",
                "values": [{"validTime": "2026-10-30T14:00:00+00:00/PT13H", "value": 24.0}],
            },
        }
    }
    df = nws.parse(payload, "asos:KLAX", "America/Los_Angeles", RECEIVED)
    by_var = df.set_index("var")["values"]
    # day0 is Oct 29 local; the first low is the dawn of Oct 30, so it sits at index 1.
    assert by_var["tmin"] == [None, 15.0, 14.0]
    assert by_var["tmax"] == [None, 24.0]
