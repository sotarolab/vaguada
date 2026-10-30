"""The store: one read contract, two implementations.

`PgStore` is Postgres through SQLAlchemy Core. `FrameStore` holds the same tables as
pandas frames in memory, for property tests and the golden backtest. Both answer the same
questions the same way, and one contract test runs against both.

Point in time: every read takes `as_of` and sees only rows with `received_at <= as_of`.
For observations and settlements the latest `received_at` per key wins. For model runs the
latest `run_at` per (model, var) wins, among runs received by `as_of`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Protocol, cast

import pandas as pd
from sqlalchemy import Engine, func, select
from sqlalchemy.dialects.postgresql import distinct_on, insert

from camanchaca_demo.store import schemas
from camanchaca_demo.store.tables import Tables, build_tables


class Store(Protocol):
    # writes: append-only tables ignore duplicates; heartbeat and stations upsert
    def write_observations(self, df: pd.DataFrame) -> int: ...
    def write_model_runs(self, df: pd.DataFrame) -> int: ...
    def write_products(self, df: pd.DataFrame) -> int: ...
    def write_settlements(self, df: pd.DataFrame) -> int: ...
    def write_markets(self, df: pd.DataFrame) -> int: ...
    def write_predictions(self, rows: list[dict[str, Any]]) -> int: ...
    def heartbeat(
        self, feed: str, ok: bool, rows: int, error: str | None, at: datetime
    ) -> None: ...

    # reads, all point in time
    def stations(self) -> pd.DataFrame: ...
    def observations(self, station_id: str, since: datetime, as_of: datetime) -> pd.DataFrame: ...
    def latest_runs(
        self, station_id: str, as_of: datetime, models: list[str] | None = None
    ) -> pd.DataFrame: ...
    def runs_between(
        self, station_id: str, since_run: datetime, as_of: datetime
    ) -> pd.DataFrame: ...
    def settlements(
        self, station_id: str, as_of: datetime, days: list[date] | None = None
    ) -> pd.DataFrame: ...
    def markets(self, station_id: str, local_day: date, as_of: datetime) -> pd.DataFrame: ...


FAR_FUTURE = datetime(2100, 1, 1, tzinfo=UTC)


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Rows for the driver, with NaN turned into None so Postgres stores NULL."""
    clean = df.astype(object).where(df.notna(), None)
    return cast(list[dict[str, Any]], clean.to_dict(orient="records"))


def drop_unchanged(
    new: pd.DataFrame, existing: pd.DataFrame, key: list[str], cols: list[str]
) -> pd.DataFrame:
    """Rows of `new` whose key already exists in `existing` with the same values are not
    corrections; drop them so a re-fetch does not add a row."""
    if new.empty or existing.empty:
        return new
    cur = existing[[*key, *cols]].rename(columns={c: f"{c}__cur" for c in cols})
    m = new.merge(cur, on=key, how="left")
    same = pd.Series(True, index=m.index)
    for c in cols:
        a, b = m[c], m[f"{c}__cur"]
        both_na = a.isna() & b.isna()
        if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
            eq = (a.astype(float) - b.astype(float)).abs() < 1e-4  # float4 storage
        else:
            eq = a == b
        same &= eq | both_na
    return new[~same.to_numpy()].reset_index(drop=True)


# ----------------------------------------------------------------------------- Postgres


class PgStore:
    def __init__(self, engine: Engine, schema: str) -> None:
        self.engine = engine
        self.t: Tables = build_tables(schema)

    # writes
    def _append(self, table: Any, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        rows = _records(df)
        pk = next(iter(table.primary_key.columns))
        with self.engine.begin() as conn:
            res = conn.execute(insert(table).on_conflict_do_nothing().returning(pk), rows)
            return len(res.fetchall())

    def write_observations(self, df: pd.DataFrame) -> int:
        new = schemas.validate_obs(df)
        for sid in new["station_id"].unique() if len(new) else []:
            cur = self.observations(str(sid), new["valid_at"].min(), FAR_FUTURE)
            new = drop_unchanged(
                new, cur, ["station_id", "valid_at", "source", "var"], ["value", "precision"]
            )
        return self._append(self.t.observations, new)

    def write_model_runs(self, df: pd.DataFrame) -> int:
        return self._append(self.t.model_runs, schemas.validate_runs(df))

    def write_products(self, df: pd.DataFrame) -> int:
        return self._append(self.t.products, schemas.validate_products(df))

    def write_settlements(self, df: pd.DataFrame) -> int:
        new = schemas.validate_settlements(df)
        for sid in new["station_id"].unique() if len(new) else []:
            cur = self.settlements(str(sid), FAR_FUTURE)
            new = drop_unchanged(
                new, cur, ["station_id", "local_day", "target"], ["value", "final"]
            )
        return self._append(self.t.settlements, new)

    def write_markets(self, df: pd.DataFrame) -> int:
        return self._append(self.t.markets, schemas.validate_markets(df))

    def write_predictions(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        pk = self.t.predictions.c.forecaster
        with self.engine.begin() as conn:
            res = conn.execute(
                insert(self.t.predictions).on_conflict_do_nothing().returning(pk), rows
            )
            return len(res.fetchall())

    def heartbeat(self, feed: str, ok: bool, rows: int, error: str | None, at: datetime) -> None:
        values: dict[str, Any] = {"feed": feed, "rows": rows, "updated_at": at}
        if ok:
            values.update(last_success=at, last_error=None)
        else:
            values.update(last_error=(error or "")[:2000])
        stmt = insert(self.t.heartbeat).values(**values)
        update = {k: v for k, v in values.items() if k != "feed"}
        with self.engine.begin() as conn:
            conn.execute(stmt.on_conflict_do_update(index_elements=["feed"], set_=update))

    def upsert_stations(self, df: pd.DataFrame) -> int:
        rows = _records(df)
        stmt = insert(self.t.stations)
        resolved = {"nws_office", "nws_grid_x", "nws_grid_y"}
        cols = {
            c.name: (
                func.coalesce(getattr(stmt.excluded, c.name), c)
                if c.name in resolved
                else getattr(stmt.excluded, c.name)
            )
            for c in self.t.stations.columns
            if c.name != "station_id"
        }
        with self.engine.begin() as conn:
            conn.execute(stmt.on_conflict_do_update(index_elements=["station_id"], set_=cols), rows)
            return len(rows)

    # reads
    def _frame(self, stmt: Any) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(stmt, conn)

    def stations(self) -> pd.DataFrame:
        return self._frame(select(self.t.stations).order_by(self.t.stations.c.station_id))

    def observations(self, station_id: str, since: datetime, as_of: datetime) -> pd.DataFrame:
        o = self.t.observations
        stmt = (
            select(o)
            .where(
                o.c.station_id == station_id,
                o.c.valid_at >= since,
                o.c.valid_at <= as_of,
                o.c.received_at <= as_of,
            )
            .ext(distinct_on(o.c.valid_at, o.c.source, o.c.var))
            .order_by(o.c.valid_at, o.c.source, o.c.var, o.c.received_at.desc())
        )
        return self._frame(stmt)

    def latest_runs(
        self, station_id: str, as_of: datetime, models: list[str] | None = None
    ) -> pd.DataFrame:
        m = self.t.model_runs
        stmt = (
            select(m)
            .where(m.c.station_id == station_id, m.c.received_at <= as_of, m.c.run_at <= as_of)
            .ext(distinct_on(m.c.model, m.c.var))
            .order_by(m.c.model, m.c.var, m.c.run_at.desc(), m.c.received_at.desc())
        )
        if models:
            stmt = stmt.where(m.c.model.in_(models))
        return self._frame(stmt)

    def runs_between(self, station_id: str, since_run: datetime, as_of: datetime) -> pd.DataFrame:
        m = self.t.model_runs
        stmt = (
            select(m)
            .where(
                m.c.station_id == station_id,
                m.c.received_at <= as_of,
                m.c.run_at >= since_run,
                m.c.run_at <= as_of,
            )
            .order_by(m.c.model, m.c.var, m.c.run_at)
        )
        return self._frame(stmt)

    def settlements(
        self, station_id: str, as_of: datetime, days: list[date] | None = None
    ) -> pd.DataFrame:
        s = self.t.settlements
        stmt = (
            select(s)
            .where(s.c.station_id == station_id, s.c.received_at <= as_of)
            .ext(distinct_on(s.c.local_day, s.c.target))
            .order_by(s.c.local_day, s.c.target, s.c.received_at.desc())
        )
        if days:
            stmt = stmt.where(s.c.local_day.in_(days))
        return self._frame(stmt)

    def markets(self, station_id: str, local_day: date, as_of: datetime) -> pd.DataFrame:
        k = self.t.markets
        stmt = (
            select(k)
            .where(
                k.c.station_id == station_id, k.c.local_day == local_day, k.c.received_at <= as_of
            )
            .ext(distinct_on(k.c.ticker))
            .order_by(k.c.ticker, k.c.as_of.desc())
        )
        return self._frame(stmt)


# ---------------------------------------------------------------------------- in memory


def _latest(df: pd.DataFrame, key: list[str], order: str = "received_at") -> pd.DataFrame:
    if df.empty:
        return df
    return (
        df.sort_values([*key, order], ascending=[*([True] * len(key)), False])
        .drop_duplicates(key, keep="first")
        .reset_index(drop=True)
    )


@dataclass
class FrameStore:
    """Same contract over pandas. Duplicate keys are ignored on write, as in Postgres."""

    obs: pd.DataFrame = field(default_factory=lambda: schemas.empty(schemas.OBS_COLUMNS))
    runs: pd.DataFrame = field(default_factory=lambda: schemas.empty(schemas.RUN_COLUMNS))
    products: pd.DataFrame = field(default_factory=lambda: schemas.empty(schemas.PRODUCT_COLUMNS))
    settle: pd.DataFrame = field(default_factory=lambda: schemas.empty(schemas.SETTLEMENT_COLUMNS))
    mkts: pd.DataFrame = field(default_factory=lambda: schemas.empty(schemas.MARKET_COLUMNS))
    preds: list[dict[str, Any]] = field(default_factory=list)
    beats: dict[str, dict[str, Any]] = field(default_factory=dict)
    station_rows: pd.DataFrame = field(
        default_factory=lambda: schemas.empty(schemas.STATION_COLUMNS)
    )

    @staticmethod
    def _append(
        existing: pd.DataFrame, new: pd.DataFrame, key: list[str]
    ) -> tuple[pd.DataFrame, int]:
        if new.empty:
            return existing, 0
        both = new.copy() if existing.empty else pd.concat([existing, new], ignore_index=True)
        before = len(existing)
        both = both.drop_duplicates(key, keep="first").reset_index(drop=True)
        return both, len(both) - before

    def write_observations(self, df: pd.DataFrame) -> int:
        new = schemas.validate_obs(df)
        for sid in new["station_id"].unique() if len(new) else []:
            cur = self.observations(str(sid), new["valid_at"].min(), FAR_FUTURE)
            new = drop_unchanged(
                new, cur, ["station_id", "valid_at", "source", "var"], ["value", "precision"]
            )
        self.obs, n = self._append(
            self.obs, new, ["station_id", "valid_at", "source", "var", "received_at"]
        )
        return n

    def write_model_runs(self, df: pd.DataFrame) -> int:
        self.runs, n = self._append(
            self.runs, schemas.validate_runs(df), ["model", "station_id", "run_at", "var"]
        )
        return n

    def write_products(self, df: pd.DataFrame) -> int:
        self.products, n = self._append(
            self.products, schemas.validate_products(df), ["pil", "issued_at"]
        )
        return n

    def write_settlements(self, df: pd.DataFrame) -> int:
        new = schemas.validate_settlements(df)
        for sid in new["station_id"].unique() if len(new) else []:
            cur = self.settlements(str(sid), FAR_FUTURE)
            new = drop_unchanged(
                new, cur, ["station_id", "local_day", "target"], ["value", "final"]
            )
        self.settle, n = self._append(
            self.settle, new, ["station_id", "local_day", "target", "received_at"]
        )
        return n

    def write_markets(self, df: pd.DataFrame) -> int:
        self.mkts, n = self._append(self.mkts, schemas.validate_markets(df), ["ticker", "as_of"])
        return n

    def write_predictions(self, rows: list[dict[str, Any]]) -> int:
        key = ("forecaster", "version", "station_id", "target", "local_day", "as_of")
        seen = {tuple(r[k] for k in key) for r in self.preds}
        n = 0
        for r in rows:
            k = tuple(r[c] for c in key)
            if k not in seen:
                self.preds.append(r)
                seen.add(k)
                n += 1
        return n

    def heartbeat(self, feed: str, ok: bool, rows: int, error: str | None, at: datetime) -> None:
        b = self.beats.setdefault(
            feed, {"feed": feed, "last_success": None, "last_error": None, "rows": 0}
        )
        b["rows"] = rows
        b["updated_at"] = at
        if ok:
            b["last_success"], b["last_error"] = at, None
        else:
            b["last_error"] = error

    def stations(self) -> pd.DataFrame:
        return self.station_rows.copy()

    def observations(self, station_id: str, since: datetime, as_of: datetime) -> pd.DataFrame:
        o = self.obs
        sel = o[
            (o.station_id == station_id)
            & (o.valid_at >= since)
            & (o.valid_at <= as_of)
            & (o.received_at <= as_of)
        ]
        return _latest(sel, ["valid_at", "source", "var"])

    def latest_runs(
        self, station_id: str, as_of: datetime, models: list[str] | None = None
    ) -> pd.DataFrame:
        r = self.runs
        sel = r[(r.station_id == station_id) & (r.received_at <= as_of) & (r.run_at <= as_of)]
        if models:
            sel = sel[sel.model.isin(models)]
        if sel.empty:
            return sel
        return (
            sel.sort_values(
                ["model", "var", "run_at", "received_at"], ascending=[True, True, False, False]
            )
            .drop_duplicates(["model", "var"], keep="first")
            .reset_index(drop=True)
        )

    def runs_between(self, station_id: str, since_run: datetime, as_of: datetime) -> pd.DataFrame:
        r = self.runs
        sel = r[
            (r.station_id == station_id)
            & (r.received_at <= as_of)
            & (r.run_at >= since_run)
            & (r.run_at <= as_of)
        ]
        return sel.sort_values(["model", "var", "run_at"]).reset_index(drop=True)

    def settlements(
        self, station_id: str, as_of: datetime, days: list[date] | None = None
    ) -> pd.DataFrame:
        s = self.settle
        sel = s[(s.station_id == station_id) & (s.received_at <= as_of)]
        if days:
            sel = sel[sel.local_day.isin(days)]
        return _latest(sel, ["local_day", "target"])

    def markets(self, station_id: str, local_day: date, as_of: datetime) -> pd.DataFrame:
        k = self.mkts
        sel = k[
            (k.station_id == station_id) & (k.local_day == local_day) & (k.received_at <= as_of)
        ]
        return _latest(sel, ["ticker"], order="as_of")
