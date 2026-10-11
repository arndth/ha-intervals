"""Abruf von intervals.icu und Anwenden von Planänderungen."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import IntervalsAuthError, IntervalsClient, IntervalsConnectionError
from .const import (
    CONF_ANTHROPIC_KEY,
    CONF_MODEL,
    CONF_RACE_DATE,
    CONF_SCAN_INTERVAL,
    DEFAULT_MODEL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_ANALYSIS_READY,
    EVENT_NEW_ACTIVITY,
    HISTORY_DAYS,
    PLAN_MARKER,
)
from .planbuilder import build_plan, summary
from .planner import Change, Session, classify, week_start
from .util import parse_date
from .store import IntervalsStore

_LOGGER = logging.getLogger(__name__)

PLAN_HORIZON_DAYS = 120

# Was als Lauf zählt. intervals.icu nimmt jede Sportart auf — in Arndts Daten
# standen "Tauchen" (0 km) und "Fußball indoor" (2,4 km bei 8:26/km) zwischen
# den Läufen und haben Wochenkilometer wie Bestzeiten verfälscht.
RUN_TYPES = ("run", "trailrun", "virtualrun", "treadmill")


def is_run(activity: dict | str | None) -> bool:
    typ = activity.get("kind") or activity.get("type") if isinstance(activity, dict) else activity
    return bool(typ) and str(typ).lower().replace(" ", "") in RUN_TYPES


class IntervalsCoordinator(DataUpdateCoordinator[dict]):
    """Hält den gemeinsamen Zustand und schreibt Planänderungen zurück."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: IntervalsClient,
        store: IntervalsStore,
    ) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
        )
        self.entry = entry
        self.client = client
        self.store = store
        self._plan: list[Session] = []

    # ── Abruf ────────────────────────────────────────────────────────────

    async def _async_update_data(self) -> dict:
        today = date.today()
        try:
            activities = await self.client.async_get_activities(
                today - timedelta(days=HISTORY_DAYS), today
            )
            wellness = await self.client.async_get_wellness(
                today - timedelta(days=HISTORY_DAYS), today
            )
            events = await self.client.async_get_events(
                today - timedelta(days=7), today + timedelta(days=PLAN_HORIZON_DAYS)
            )
        except IntervalsAuthError as err:
            # Kein UpdateFailed: der Schlüssel ist weg, Wiederholen hilft nicht.
            from homeassistant.exceptions import ConfigEntryAuthFailed

            raise ConfigEntryAuthFailed(str(err)) from err
        except IntervalsConnectionError as err:
            raise UpdateFailed(str(err)) from err

        neu = await self.store.async_upsert_activities(activities)
        await self.store.async_upsert_wellness(wellness)
        await self.store.async_replace_plan(
            [self._plan_row(e) for e in events if self._is_planned(e)]
        )
        self._plan = await self._load_plan()

        # Neue Trainings melden — darauf hängt sich die Analyse-Automation
        # (und ein externer Agent, wenn er will).
        for aid in neu:
            row = next((a for a in activities if str(a.get("id")) == aid), {})
            self.hass.bus.async_fire(
                EVENT_NEW_ACTIVITY,
                {
                    "activity_id": aid,
                    "entry_id": self.entry.entry_id,
                    "name": row.get("name"),
                    "km": round((row.get("distance") or 0) / 1000.0, 2),
                    "last": row.get("icu_training_load"),
                    "tag": (row.get("start_date_local") or "")[:10],
                },
            )

        woche = await self.store.async_query(
            "SELECT COALESCE(SUM(km), 0) AS km FROM activities "
            "WHERE day >= ? AND LOWER(REPLACE(kind, ' ', '')) IN "
            "('run','trailrun','virtualrun','treadmill')",
            (week_start(today).isoformat(),),
        )

        latest = wellness[-1] if wellness else {}
        ctl, atl = latest.get("ctl"), latest.get("atl")
        return {
            "stand": date.today().isoformat(),
            "wochen_km": round(woche[0]["km"], 1) if woche else 0.0,
            "ctl": ctl,
            "atl": atl,
            "form": (ctl - atl) if ctl is not None and atl is not None else None,
            "aktivitaeten": len(activities),
            "neue_aktivitaeten": neu,
            "geplant": len(self._plan),
        }

    # ── Plan ─────────────────────────────────────────────────────────────

    @staticmethod
    def _is_planned(event: dict) -> bool:
        """Nur geplante Workouts, keine Notizen, Rennen oder Urlaubseinträge."""
        return event.get("category") in (None, "WORKOUT") and bool(
            event.get("start_date_local")
        )

    @staticmethod
    def _plan_row(e: dict) -> tuple:
        name = e.get("name") or ""
        desc = e.get("description") or ""
        load = e.get("icu_training_load") or 0
        km = (e.get("distance") or 0) / 1000.0
        return (
            str(e.get("id")),
            (e.get("start_date_local") or "")[:10],
            classify(name, desc, load, km),
            name,
            load,
            km,
            desc,
            json.dumps(e, ensure_ascii=False),
        )

    async def _load_plan(self) -> list[Session]:
        rows = await self.store.async_query(
            "SELECT id, day, kind, name, load, km, description "
            "FROM plan_events ORDER BY day"
        )
        return [
            Session(
                event_id=r["id"],
                day=date.fromisoformat(r["day"]),
                kind=r["kind"],
                name=r["name"] or "",
                load=int(r["load"] or 0),
                km=float(r["km"] or 0.0),
                description=r["description"] or "",
            )
            for r in rows
            if r["day"]
        ]

    def planned_sessions(self) -> list[Session]:
        return list(self._plan)

    def target_week_load(self, any_day: date) -> int | None:
        """Sollast der Woche = Summe der ursprünglich geplanten Einheiten.

        Bewusst der Plan und nicht der Durchschnitt: die Regel soll messen,
        wie weit ein Zug vom *Plan* abweicht, nicht vom Mittelwert.
        """
        start = week_start(any_day)
        end = start + timedelta(days=6)
        total = sum(s.load for s in self._plan if start <= s.day <= end)
        return total or None

    async def async_apply_changes(self, changes: list[Change]) -> None:
        """Änderungen nach intervals.icu schreiben — von dort auf die Uhr."""
        by_id = {s.event_id: s for s in self._plan}
        for ch in changes:
            session = by_id.get(ch.event_id)
            try:
                if ch.action == "delete":
                    await self.client.async_delete_event(ch.event_id)
                    detail = f"gestrichen ({session.name if session else '?'})"
                elif ch.action == "move" and ch.new_day:
                    await self.client.async_update_event(
                        ch.event_id,
                        {"start_date_local": f"{ch.new_day.isoformat()}T00:00:00"},
                    )
                    detail = f"verschoben auf {ch.new_day.isoformat()}"
                else:
                    continue
            except IntervalsConnectionError:
                _LOGGER.exception("Änderung an %s fehlgeschlagen", ch.event_id)
                raise
            await self.store.async_log_plan(ch.event_id, ch.action, detail)

        await self.async_request_refresh()

    # ── KI ───────────────────────────────────────────────────────────────

    def _anthropic_config(self) -> tuple[str | None, str]:
        return (
            self.entry.options.get(CONF_ANTHROPIC_KEY) or None,
            self.entry.options.get(CONF_MODEL, DEFAULT_MODEL),
        )

    async def async_analyse(self, activity_id: str | None) -> dict:
        """Eine Aktivität von Claude bewerten lassen."""
        key, model = self._anthropic_config()
        if not key:
            return {
                "ok": False,
                "grund": "Kein Anthropic-Schlüssel hinterlegt — Analyse übersprungen.",
            }

        if not activity_id:
            rows = await self.store.async_query(
                "SELECT id FROM activities ORDER BY day DESC LIMIT 1"
            )
            if not rows:
                return {"ok": False, "grund": "Keine Aktivität vorhanden."}
            activity_id = rows[0]["id"]

        from .analysis import async_analyse_activity

        result = await async_analyse_activity(self, str(activity_id), key, model)
        self.hass.bus.async_fire(
            EVENT_ANALYSIS_READY,
            {"activity_id": activity_id, "entry_id": self.entry.entry_id, **result},
        )
        return result

    async def async_replan(self, ab: date, grund: str) -> dict:
        """Die Restwoche neu planen lassen.

        Nur hierfür wird ein Modell befragt — das Verschieben selbst erledigt
        das Regelwerk in planner.py.
        """
        key, model = self._anthropic_config()
        if not key:
            return {
                "ok": False,
                "grund": "Kein Anthropic-Schlüssel hinterlegt — Umplanung übersprungen.",
            }
        from .analysis import async_replan_week

        return await async_replan_week(self, ab, grund, key, model)

    def cfg(self, key, default=None):
        """Einstellung lesen: Optionen haben Vorrang vor den Einrichtungsdaten.

        Die Wettkampfangaben werden bei der Einrichtung in `data` geschrieben
        und später über die Optionen geändert. Ohne diesen Rückfall würde eine
        Änderung still wirkungslos bleiben.
        """
        return self.entry.options.get(key, self.entry.data.get(key, default))

    @property
    def race_date(self) -> date | None:
        """Renndatum, nachsichtig gelesen.

        In v0.1.0 stand hier `date.fromisoformat`. Eine deutsche Eingabe wie
        `10.01.2026` hat damit den Dienst mit 500 beendet und das Anlegen von
        `sensor.tage_bis_zum_rennen` verhindert. Ein unlesbares Datum darf
        höchstens "kein Renntag" bedeuten, nie einen Absturz.
        """
        return parse_date(self.cfg(CONF_RACE_DATE))

    # ── Daten fürs Panel ─────────────────────────────────────────────────

    # Distanzklassen für die Bestzeiten. Ein Lauf zählt, wenn seine Distanz
    # innerhalb ±7 % der Klasse liegt — so landet ein 10,4-km-Lauf bei 10 km
    # und ein 13,0-km-Lauf nicht versehentlich dort.
    DISTANCE_CLASSES = (5.0, 10.0, 13.0, 15.0, 21.0975, 42.195)

    async def async_panel_data(self, tage: int = 91) -> dict:
        """Alles, was das Dashboard braucht, in einem Aufruf."""
        heute = date.today()
        ab = heute - timedelta(days=tage)

        verlauf = await self.store.async_query(
            "SELECT day, ctl, atl, form FROM wellness "
            "WHERE day >= ? ORDER BY day",
            (ab.isoformat(),),
        )
        aktivitaeten = await self.store.async_query(
            "SELECT id, day, name, kind, km, seconds, load, hr_avg, pace_s_km, raw "
            "FROM activities WHERE day >= ? ORDER BY day DESC",
            (ab.isoformat(),),
        )
        analysen = await self.store.async_query(
            "SELECT activity_id, created, model, verdict, prose "
            "FROM analyses ORDER BY created DESC LIMIT 20"
        )

        laeufe = [a for a in aktivitaeten if is_run(a)]
        andere = len(aktivitaeten) - len(laeufe)

        return {
            "stand": heute.isoformat(),
            "andere_sportarten": andere,
            "renntag": self.race_date.isoformat() if self.race_date else None,
            "tage_bis_rennen": (self.race_date - heute).days
            if self.race_date
            else None,
            "verlauf": verlauf,
            "wochen": self._weekly(laeufe),
            "trainings": [{k: a[k] for k in a if k != "raw"} for a in laeufe[:60]],
            "bestzeiten": self._best_efforts(laeufe),
            "plan": [
                {
                    "event_id": s.event_id,
                    "tag": s.day.isoformat(),
                    "art": s.kind,
                    "name": s.name,
                    "last": s.load,
                    "km": s.km,
                    "beschreibung": s.description,
                }
                for s in self._plan
            ],
            "analysen": [
                {
                    **a,
                    "verdict": json.loads(a["verdict"]) if a.get("verdict") else None,
                }
                for a in analysen
            ],
        }

    def _weekly(self, aktivitaeten: list[dict]) -> list[dict]:
        """Wochenaggregate inklusive Zonenzeiten.

        Die Zonenzeiten stehen nur im Rohobjekt von intervals.icu
        (`icu_hr_zone_times`, Sekunden je Zone) — dafür wird das gespeicherte
        JSON ausgepackt, statt eine weitere Spalte zu führen, die bei jeder
        Schemaänderung nachgezogen werden müsste.
        """
        aus: dict[str, dict] = {}
        for a in aktivitaeten:
            if not a.get("day"):
                continue
            tag = date.fromisoformat(a["day"])
            start = week_start(tag).isoformat()
            w = aus.setdefault(
                start,
                {"start": start, "km": 0.0, "last": 0, "sekunden": 0, "zonen": [0] * 5},
            )
            w["km"] += a.get("km") or 0.0
            w["last"] += a.get("load") or 0
            w["sekunden"] += a.get("seconds") or 0
            try:
                roh = json.loads(a.get("raw") or "{}")
                zonen = roh.get("icu_hr_zone_times") or []
                for i, sek in enumerate(zonen[:5]):
                    w["zonen"][i] += int(sek or 0) // 60  # Minuten
            except (ValueError, TypeError):
                pass

        # Sollwerte aus dem Plan danebenlegen, damit das Diagramm Soll/Ist
        # zeigen kann, ohne einen zweiten Aufruf.
        plan_km: dict[str, float] = {}
        for s in self._plan:
            plan_km[week_start(s.day).isoformat()] = (
                plan_km.get(week_start(s.day).isoformat(), 0.0) + s.km
            )

        wochen = []
        for start, w in sorted(aus.items()):
            w["km"] = round(w["km"], 1)
            w["soll_km"] = round(plan_km.get(start, 0.0), 1) or None
            wochen.append(w)
        return wochen

    def _best_efforts(self, aktivitaeten: list[dict]) -> list[dict]:
        """Schnellste Gesamtzeit je Distanzklasse.

        Achtung, das ist **nicht** dasselbe wie eine echte Bestzeit: gemessen
        wird der Gesamtschnitt eines Laufs, nicht das schnellste Teilstück
        darin. Für Letzteres braucht es die Pace-Dauer-Kurve aus den Streams
        — die ist noch nicht gebaut. Das Panel beschriftet den Wert
        entsprechend, damit niemand ihn für eine Rennbestzeit hält.
        """
        beste: list[dict] = []
        for ziel in self.DISTANCE_CLASSES:
            lo, hi = ziel * 0.93, ziel * 1.07
            treffer = [
                a
                for a in aktivitaeten
                if a.get("km") and lo <= a["km"] <= hi and a.get("seconds")
            ]
            if not treffer:
                continue
            best = min(treffer, key=lambda a: a["seconds"] / a["km"])
            beste.append(
                {
                    "distanz_km": ziel,
                    "activity_id": best["id"],
                    "tag": best["day"],
                    "name": best["name"],
                    "km": round(best["km"], 2),
                    "sekunden": best["seconds"],
                    "pace_s_km": round(best["seconds"] / best["km"], 1),
                    "anzahl_laeufe": len(treffer),
                }
            )
        return beste

    # ── Plan erzeugen ────────────────────────────────────────────────────

    async def async_build_plan(self, dry_run: bool, race_pace_s: int) -> dict:
        """Plan rechnen und auf Wunsch nach intervals.icu schreiben.

        Wiederholbar: vor dem Schreiben werden die eigenen Einträge im
        Planungsfenster gelöscht. Erkannt werden sie an PLAN_MARKER in der
        Beschreibung — von Hand angelegte Einheiten bleiben stehen.
        """
        renntag = self.race_date
        if not renntag:
            return {"ok": False, "grund": "Kein Renndatum gesetzt."}

        plan = build_plan(renntag, race_pace_s)
        wochen = summary(plan)
        vorschau = {
            "ok": True,
            "trocken": dry_run,
            "renntag": renntag.isoformat(),
            "ziel_pace": f"{race_pace_s // 60}:{race_pace_s % 60:02d}",
            "einheiten": len(plan),
            "davon_kuenftig": len([s for s in plan if s.day >= date.today()]),
            "gesamt_km": round(sum(s.km for s in plan), 1),
            "wochen": wochen,
            "plan": [
                {
                    "tag": s.day.isoformat(),
                    "woche": s.week,
                    "phase": s.phase,
                    "art": s.kind,
                    "name": s.name,
                    "km": s.km,
                    "last": s.load,
                    "beschreibung": s.description,
                }
                for s in plan
            ],
        }
        if dry_run:
            return vorschau

        # Nur die Zukunft anfassen. Ohne das würde ein erneuter Aufruf mitten
        # im Plan die bereits vergangenen Wochen löschen und neu schreiben —
        # damit wäre nicht mehr nachvollziehbar, was ursprünglich geplant war
        # und was tatsächlich gelaufen ist. Genau das ist der Unterschied
        # zwischen "Plan anpassen" und "Geschichte umschreiben".
        heute = date.today()
        kuenftig = [s for s in plan if s.day >= heute]
        if not kuenftig:
            return {**vorschau, "ok": False, "grund": "Alle Planwochen liegen in der Vergangenheit."}

        von, bis = min(s.day for s in kuenftig), max(s.day for s in kuenftig)
        entfernt = 0
        try:
            bestehend = await self.client.async_get_events(von, bis)
        except IntervalsConnectionError as err:
            return {**vorschau, "ok": False, "grund": f"Kalender nicht lesbar: {err}"}

        for e in bestehend:
            if PLAN_MARKER in (e.get("description") or ""):
                try:
                    await self.client.async_delete_event(e["id"])
                    entfernt += 1
                except IntervalsConnectionError:
                    _LOGGER.warning("Alter Eintrag %s nicht löschbar", e.get("id"))

        geschrieben, fehler = 0, []
        for s in kuenftig:
            payload = {
                "start_date_local": f"{s.day.isoformat()}T00:00:00",
                "category": "WORKOUT",
                "type": "Run",
                "name": s.name,
                "description": f"{s.description}\n\n{PLAN_MARKER} Woche {s.week} · {s.phase}",
                "moving_time": int(s.km * race_pace_s * 1.15),
                "distance": int(s.km * 1000),
                "icu_training_load": s.load,
            }
            try:
                await self.client.async_create_event(payload)
                geschrieben += 1
            except IntervalsConnectionError as err:
                fehler.append({"tag": s.day.isoformat(), "fehler": str(err)})

        await self.store.async_log_plan(
            "-", "plan_erstellt", f"{geschrieben} Einheiten, {entfernt} ersetzt"
        )
        await self.async_request_refresh()
        return {
            **vorschau,
            "trocken": False,
            "geschrieben": geschrieben,
            "ersetzt": entfernt,
            "uebersprungen_vergangenheit": len(plan) - len(kuenftig),
            "fehler": fehler,
        }
