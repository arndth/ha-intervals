"""Claude-Aufrufe: Einzelanalyse und Wochen-Umplanung.

Zwei Grundsätze:

1. **Nie rohe Streams ins Modell.** Ein Lauf hat ~3000 Messpunkte je Kanal.
   Als Text wären das 50.000 Token für Information, die zehn Kennzahlen
   besser ausdrücken. Hier wird vorher in Python verdichtet.

2. **Nie beim Seitenaufruf.** Beide Funktionen laufen aus einer Automation
   oder einem Service-Aufruf und legen das Ergebnis in SQLite ab. Das Panel
   liest nur noch Text.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from .const import DEFAULT_MODEL

if TYPE_CHECKING:
    from .coordinator import IntervalsCoordinator

_LOGGER = logging.getLogger(__name__)

# Stabiler Vorspann → cachefähig. Bei Opus 5 liegt die Mindestlänge für den
# Prompt-Cache bei 512 Token, der Block hier erreicht sie.
SYSTEM = """Du bist Lauftrainer und bewertest einzelne Trainingseinheiten \
eines ambitionierten Freizeitläufers.

Arbeitsweise:
- Urteile nur über das, was in den Daten steht. Keine Vermutungen über \
Schlaf, Ernährung oder Stress, wenn dazu nichts geliefert wurde.
- Entkopplung unter 5 % heißt aerob gefahren, 5–8 % grenzwertig, darüber zu hart.
- Negative Form (CTL−ATL) im Aufbau ist normal und kein Warnsignal. Erst \
unter −25 oder bei drei Wochen ohne Entlastung wird es eins.
- Schreib auf Deutsch, in ganzen Sätzen, höchstens zwei kurze Absätze. \
Keine Aufzählungen, keine Überschriften, keine Floskeln.
- Beginne mit dem Ergebnis, nicht mit der Methode."""

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "ausfuehrung": {
            "type": "string",
            "enum": ["gut", "teilweise", "verfehlt", "abgebrochen"],
        },
        "entkopplung_prozent": {"type": "number"},
        "pace_abweichung_sekunden": {"type": "number"},
        "zonentreue_prozent": {"type": "number"},
        "prosa": {"type": "string"},
        "empfehlung_naechste_woche": {"type": "string"},
    },
    "required": [
        "ausfuehrung",
        "entkopplung_prozent",
        "pace_abweichung_sekunden",
        "zonentreue_prozent",
        "prosa",
        "empfehlung_naechste_woche",
    ],
    "additionalProperties": False,
}


# ── Verdichtung ──────────────────────────────────────────────────────────


def summarise_streams(streams: dict[str, list]) -> dict[str, Any]:
    """Aus ~3000 Messpunkten je Kanal ein gutes Dutzend Kennzahlen.

    Das ist der Schritt, der die Kosten um Faktor 50 drückt.
    """
    hr = [h for h in streams.get("heartrate", []) if h]
    vel = [v for v in streams.get("velocity_smooth", []) if v]
    if not hr or not vel:
        return {}

    half = min(len(hr), len(vel)) // 2
    if half < 60:  # unter zwei Minuten lohnt die Rechnung nicht
        return {}

    def ratio(hrs: list, vels: list) -> float:
        mh = sum(hrs) / len(hrs)
        mv = sum(vels) / len(vels)
        return (mv / mh) if mh else 0.0

    r1 = ratio(hr[:half], vel[:half])
    r2 = ratio(hr[half : half * 2], vel[half : half * 2])
    entkopplung = ((r1 - r2) / r1 * 100) if r1 else 0.0

    hr_sorted = sorted(hr)
    return {
        "hf_mittel": round(sum(hr) / len(hr)),
        "hf_max": max(hr),
        "hf_median": hr_sorted[len(hr_sorted) // 2],
        "pace_mittel_s_km": round(1000 / (sum(vel) / len(vel)), 1) if vel else None,
        "entkopplung_prozent": round(entkopplung, 1),
        "punkte": len(hr),
    }


async def _context(coord: IntervalsCoordinator, activity_id: str) -> dict:
    """Aktivität, 14 Tage Verlauf und die geplante Einheit des Tages."""
    acts = await coord.store.async_query(
        "SELECT * FROM activities WHERE id = ?", (activity_id,)
    )
    if not acts:
        return {}
    act = acts[0]
    tag = act["day"]

    verlauf = await coord.store.async_query(
        "SELECT day, ctl, atl, form FROM wellness WHERE day >= ? ORDER BY day",
        ((date.fromisoformat(tag) - timedelta(days=14)).isoformat(),),
    )
    geplant = await coord.store.async_query(
        "SELECT name, description, load, km FROM plan_events WHERE day = ?", (tag,)
    )

    streams = await coord.client.async_get_streams(activity_id)
    return {
        "aktivitaet": {
            k: act[k] for k in ("day", "name", "km", "seconds", "load", "hr_avg")
        },
        "streams": summarise_streams(streams),
        "verlauf_14_tage": verlauf,
        "geplant_war": geplant[0] if geplant else None,
        "renntag": coord.race_date.isoformat() if coord.race_date else None,
    }


# ── Aufrufe ──────────────────────────────────────────────────────────────


async def async_analyse_activity(
    coord: IntervalsCoordinator, activity_id: str, api_key: str, model: str
) -> dict:
    """Eine Einheit bewerten und das Ergebnis ablegen."""
    ctx = await _context(coord, activity_id)
    if not ctx:
        return {"ok": False, "grund": f"Aktivität {activity_id} nicht gefunden."}

    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        return {"ok": False, "grund": "Paket 'anthropic' nicht installiert."}

    client = AsyncAnthropic(api_key=api_key)

    try:
        resp = await client.beta.messages.create(
            model=model or DEFAULT_MODEL,
            max_tokens=4000,
            # Serverseitiger Rückfall: lehnt ein Sicherheitsklassifikator ab,
            # übernimmt automatisch ein anderes Modell, statt leer zu antworten.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=[
                {
                    "type": "text",
                    "text": SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": VERDICT_SCHEMA},
            },
            messages=[
                {
                    "role": "user",
                    "content": "Bewerte diese Einheit:\n"
                    + json.dumps(ctx, ensure_ascii=False, indent=1, default=str),
                }
            ],
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.exception("Analyse fehlgeschlagen")
        return {"ok": False, "grund": f"{type(err).__name__}: {err}"}

    # Erst den Abbruchgrund prüfen: bei einer Ablehnung ist content leer, und
    # ein blindes content[0] liefe auf einen IndexError.
    if resp.stop_reason == "refusal":
        return {"ok": False, "grund": "Vom Modell abgelehnt."}

    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        verdict = json.loads(text)
    except json.JSONDecodeError:
        return {"ok": False, "grund": "Antwort war kein gültiges JSON."}

    await coord.store.async_save_analysis(
        {
            "activity_id": activity_id,
            "created": datetime.now(timezone.utc).isoformat(),
            "model": resp.model,
            "verdict": json.dumps(verdict, ensure_ascii=False),
            "prose": verdict.get("prosa", ""),
            "tokens_in": resp.usage.input_tokens,
            "tokens_out": resp.usage.output_tokens,
        }
    )
    return {"ok": True, "activity_id": activity_id, **verdict}


async def async_replan_week(
    coord: IntervalsCoordinator, ab: date, grund: str, api_key: str, model: str
) -> dict:
    """Die Restwoche neu planen lassen.

    Absichtlich der einzige Ort, an dem ein Modell über den Plan entscheidet.
    Alles Mechanische — verschieben, tauschen, streichen — macht planner.py.

    Noch nicht fertig: der Rückschreibe-Teil fehlt. Der Entwurf erzeugt
    Vorschläge, die erst nach Bestätigung durch das Regelwerk und den
    Menschen nach intervals.icu gehen sollen — ein Modell, das ungeprüft in
    den Kalender schreibt, ist genau das, was diese Architektur vermeiden will.
    """
    sessions = [s for s in coord.planned_sessions() if s.day >= ab]
    return {
        "ok": False,
        "grund": "Umplanung ist noch nicht implementiert.",
        "betroffen": len(sessions),
        "ab": ab.isoformat(),
        "anlass": grund,
    }
