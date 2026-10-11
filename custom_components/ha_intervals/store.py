"""Lokale Ablage: eine SQLite-Datei unter /config/ha_intervals/.

Warum SQLite und nicht die vorhandene InfluxDB: Läufe sind Ereignisse mit
Attributen, keine gleichmäßig gesampelten Messreihen. Und warum überhaupt
lokal, wo intervals.icu alles hat — für zwei Dinge:

  1. Das Panel soll sofort rendern und auch dann funktionieren, wenn
     intervals.icu gerade nicht erreichbar ist.
  2. Für das, was intervals.icu nicht kennt: KI-Analysen, Planbegründungen,
     Pace-Dauer-Kurven, Verlauf der Planänderungen.

Nicht in die Recorder-Datenbank schreiben. Eigene Datei, eigenes Schema.

sqlite3 ist blockierend, deshalb läuft jeder Zugriff über den Executor.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    id          TEXT PRIMARY KEY,
    day         TEXT NOT NULL,
    name        TEXT,
    kind        TEXT,
    km          REAL,
    seconds     INTEGER,
    load        INTEGER,
    hr_avg      INTEGER,
    pace_s_km   REAL,
    raw         TEXT
);
CREATE INDEX IF NOT EXISTS ix_activities_day ON activities(day);

CREATE TABLE IF NOT EXISTS wellness (
    day         TEXT PRIMARY KEY,
    ctl         REAL,
    atl         REAL,
    form        REAL,
    resting_hr  INTEGER,
    hrv         REAL,
    weight      REAL,
    raw         TEXT
);

CREATE TABLE IF NOT EXISTS plan_events (
    id          TEXT PRIMARY KEY,
    day         TEXT NOT NULL,
    kind        TEXT,
    name        TEXT,
    load        INTEGER,
    km          REAL,
    description TEXT,
    syntax      TEXT,
    raw         TEXT
);
CREATE INDEX IF NOT EXISTS ix_plan_day ON plan_events(day);

CREATE TABLE IF NOT EXISTS analyses (
    activity_id TEXT PRIMARY KEY,
    created     TEXT NOT NULL,
    model       TEXT,
    verdict     TEXT,   -- JSON: strukturiertes Urteil
    prose       TEXT,
    tokens_in   INTEGER,
    tokens_out  INTEGER
);

-- Teuer zu rechnen, billig zu speichern: bestes gleitendes Mittel je Dauer.
CREATE TABLE IF NOT EXISTS pace_curve (
    activity_id TEXT NOT NULL,
    seconds     INTEGER NOT NULL,
    pace_s_km   REAL NOT NULL,
    PRIMARY KEY (activity_id, seconds)
);

-- Verlauf der Planänderungen, damit nachvollziehbar bleibt, warum der Plan
-- heute so aussieht. Ein Agent kann hier ebenfalls mitlesen.
CREATE TABLE IF NOT EXISTS plan_log (
    ts          TEXT NOT NULL,
    event_id    TEXT,
    action      TEXT,
    detail      TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key         TEXT PRIMARY KEY,
    value       TEXT
);
"""


class IntervalsStore:
    """Schmale Hülle um sqlite3, alle Aufrufe im Executor."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._path = Path(hass.config.path("ha_intervals")) / f"{entry_id}.db"
        self._conn: sqlite3.Connection | None = None

    # ── Lebenszyklus ─────────────────────────────────────────────────────

    async def async_init(self) -> None:
        await self._hass.async_add_executor_job(self._init)

    def _init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False, weil der Executor wechselnde Threads nutzt;
        # Serialisierung übernimmt sqlite3 selbst im Standardmodus.
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        # Bestehende Ablagen nachziehen. SQLite kennt kein "ADD COLUMN IF NOT
        # EXISTS"; ein zweiter Lauf wirft OperationalError, und das ist hier
        # der Normalfall, kein Fehler.
        for tabelle, spalte, typ in (("plan_events", "syntax", "TEXT"),):
            try:
                self._conn.execute(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {typ}")
            except sqlite3.OperationalError:
                pass
        self._conn.commit()

    async def async_close(self) -> None:
        if self._conn:
            await self._hass.async_add_executor_job(self._conn.close)
            self._conn = None

    # ── Schreiben ────────────────────────────────────────────────────────

    async def async_upsert_activities(self, rows: list[dict]) -> list[str]:
        """Gibt die IDs zurück, die vorher nicht da waren — daraus wird das
        Event `ha_intervals_training_neu`."""
        return await self._hass.async_add_executor_job(self._upsert_activities, rows)

    def _upsert_activities(self, rows: list[dict]) -> list[str]:
        assert self._conn
        cur = self._conn.cursor()
        known = {r[0] for r in cur.execute("SELECT id FROM activities")}
        neu: list[str] = []
        for a in rows:
            aid = str(a.get("id"))
            if aid not in known:
                neu.append(aid)
            seconds = a.get("moving_time") or a.get("elapsed_time") or 0
            km = (a.get("distance") or 0) / 1000.0
            cur.execute(
                """INSERT INTO activities
                   (id, day, name, kind, km, seconds, load, hr_avg, pace_s_km, raw)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     day=excluded.day, name=excluded.name, kind=excluded.kind,
                     km=excluded.km, seconds=excluded.seconds, load=excluded.load,
                     hr_avg=excluded.hr_avg, pace_s_km=excluded.pace_s_km,
                     raw=excluded.raw""",
                (
                    aid,
                    (a.get("start_date_local") or "")[:10],
                    a.get("name"),
                    a.get("type"),
                    km,
                    seconds,
                    a.get("icu_training_load") or 0,
                    a.get("average_heartrate"),
                    (seconds / km) if km else None,
                    json.dumps(a, ensure_ascii=False),
                ),
            )
        self._conn.commit()
        return neu

    async def async_upsert_wellness(self, rows: list[dict]) -> None:
        await self._hass.async_add_executor_job(self._upsert_wellness, rows)

    def _upsert_wellness(self, rows: list[dict]) -> None:
        assert self._conn
        cur = self._conn.cursor()
        for w in rows:
            ctl, atl = w.get("ctl"), w.get("atl")
            cur.execute(
                """INSERT INTO wellness
                   (day, ctl, atl, form, resting_hr, hrv, weight, raw)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(day) DO UPDATE SET
                     ctl=excluded.ctl, atl=excluded.atl, form=excluded.form,
                     resting_hr=excluded.resting_hr, hrv=excluded.hrv,
                     weight=excluded.weight, raw=excluded.raw""",
                (
                    w.get("id"),  # intervals.icu nutzt das Datum als id
                    ctl,
                    atl,
                    (ctl - atl) if ctl is not None and atl is not None else None,
                    w.get("restingHR"),
                    w.get("hrv"),
                    w.get("weight"),
                    json.dumps(w, ensure_ascii=False),
                ),
            )
        self._conn.commit()

    async def async_replace_plan(self, rows: list[dict]) -> None:
        """Plan vollständig ersetzen — intervals.icu ist die Wahrheit."""
        await self._hass.async_add_executor_job(self._replace_plan, rows)

    def _replace_plan(self, rows: list[dict]) -> None:
        assert self._conn
        cur = self._conn.cursor()
        cur.execute("DELETE FROM plan_events")
        cur.executemany(
            """INSERT INTO plan_events
               (id, day, kind, name, load, km, description, syntax, raw)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        self._conn.commit()

    async def async_log_plan(self, event_id: str, action: str, detail: str) -> None:
        await self._hass.async_add_executor_job(self._log_plan, event_id, action, detail)

    def _log_plan(self, event_id: str, action: str, detail: str) -> None:
        assert self._conn
        from datetime import datetime, timezone

        self._conn.execute(
            "INSERT INTO plan_log (ts, event_id, action, detail) VALUES (?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), event_id, action, detail),
        )
        self._conn.commit()

    async def async_save_analysis(self, row: dict) -> None:
        await self._hass.async_add_executor_job(self._save_analysis, row)

    def _save_analysis(self, row: dict) -> None:
        assert self._conn
        self._conn.execute(
            """INSERT INTO analyses
               (activity_id, created, model, verdict, prose, tokens_in, tokens_out)
               VALUES (:activity_id,:created,:model,:verdict,:prose,:tokens_in,:tokens_out)
               ON CONFLICT(activity_id) DO UPDATE SET
                 created=excluded.created, model=excluded.model,
                 verdict=excluded.verdict, prose=excluded.prose,
                 tokens_in=excluded.tokens_in, tokens_out=excluded.tokens_out""",
            row,
        )
        self._conn.commit()

    # ── Lesen ────────────────────────────────────────────────────────────

    async def async_query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        return await self._hass.async_add_executor_job(self._query, sql, params)

    def _query(self, sql: str, params: tuple) -> list[dict[str, Any]]:
        assert self._conn
        return [dict(r) for r in self._conn.execute(sql, params)]
