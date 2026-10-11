"""Erzeugt einen periodisierten Trainingsplan.

Rein und testbar: keine Home-Assistant-Importe, keine Netzwerkaufrufe. Wer
den Plan schreibt, ist der Koordinator — hier wird er nur berechnet.

Warum ein Generator und kein Modellaufruf: Periodisierung ist Arithmetik mit
bekannten Regeln. Ein Modell würde bei gleicher Eingabe unterschiedliche
Pläne liefern, ließe sich nicht nachrechnen und kostet Geld. Das Urteil
bleibt dem Modell vorbehalten — etwa wenn eine Woche nicht mehr aufgeht
(siehe analysis.async_replan_week).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .const import KIND_EASY, KIND_LONG, KIND_QUALITY

# ── Tempobereiche, abgeleitet von der angestrebten Renn-Pace ─────────────
# Faktoren auf die Renn-Pace. Die Werte folgen den üblichen Bereichen für
# einen Wettkampf zwischen 10 km und Halbmarathon.
PACE_FACTORS = {
    "renntempo": 1.00,
    "schwelle": 1.04,   # etwas langsamer als Renntempo über diese Distanz
    "intervall": 0.93,  # VO2max-Bereich
    "locker": 1.22,
    "longrun": 1.16,
}


@dataclass(frozen=True)
class PlannedSession:
    day: date
    kind: str
    name: str
    km: float
    load: int
    description: str
    week: int
    phase: str


# ── Wochenvorlage ────────────────────────────────────────────────────────
# Je Woche: (Phase, Qualitätseinheit, lockere Einheit, lange Einheit)
# Einheit = (Name, km, Beschreibungsschlüssel)
#
# Die ersten vier Wochen enthalten bewusst *keine* Qualität. Nach fünf Wochen
# Pause ist Tempoarbeit in Woche 1 der schnellste Weg zu einer Verletzung;
# erst muss die Grundlast zurück.
WEEKS_13 = [
    # Phase          Dienstag                   Donnerstag           Sonntag
    ("Wiederaufbau", ("Locker", 5, "locker"),   ("Locker", 5, "locker"),   ("Dauerlauf", 7, "longrun")),
    ("Wiederaufbau", ("Locker", 6, "locker"),   ("Locker", 6, "locker"),   ("Dauerlauf", 8, "longrun")),
    ("Wiederaufbau", ("Locker", 6, "steig"),    ("Locker", 7, "locker"),   ("Dauerlauf", 10, "longrun")),
    ("Wiederaufbau", ("Locker", 5, "locker"),   ("Locker", 6, "locker"),   ("Dauerlauf", 7, "longrun")),
    ("Entwicklung",  ("Tempo", 7, "tempo3x5"),  ("Locker", 7, "locker"),   ("Longrun", 11, "longrun")),
    ("Entwicklung",  ("Tempo", 8, "tempo4x5"),  ("Locker", 7, "locker"),   ("Longrun", 12, "longrun")),
    ("Entwicklung",  ("Intervall", 8, "int5x1000"), ("Locker", 8, "locker"), ("Longrun", 14, "longrun")),
    ("Entwicklung",  ("Tempo", 6, "tempo2x6"),  ("Locker", 6, "locker"),   ("Dauerlauf", 10, "longrun")),
    ("Entwicklung",  ("Intervall", 9, "int6x1000"), ("Locker", 8, "locker"), ("Longrun", 15, "longrun")),
    ("Schärfung",    ("Schwelle", 9, "schwelle2x15"), ("Locker", 8, "locker"), ("Longrun", 16, "longrun")),
    ("Schärfung",    ("Renntempo", 9, "rt3x2000"), ("Locker", 8, "locker"), ("Longrun", 14, "longrun_rt")),
    ("Schärfung",    ("Renntempo", 8, "rt2x2000"), ("Locker", 7, "locker"), ("Dauerlauf", 12, "longrun")),
    ("Taper",        ("Locker", 6, "steig"),    ("Locker", 5, "locker"),   ("WETTKAMPF", 13, "rennen")),
]

# Belastungsfaktoren je Einheitentyp (Last ≈ km × Faktor). Grobe Schätzung,
# intervals.icu rechnet später die tatsächliche Last aus den Messdaten.
LOAD_FACTOR = {
    KIND_EASY: 6.0,
    KIND_LONG: 6.5,
    KIND_QUALITY: 8.5,
}


def _pace(race_pace_s: int, key: str) -> int:
    return round(race_pace_s * PACE_FACTORS[key])


def _mmss(sec: int) -> str:
    return f"{sec // 60}:{sec % 60:02d}"


def _describe(key: str, km: float, rp: int) -> str:
    """Beschreibungstext mit konkreten Tempovorgaben."""
    lo, lr = _pace(rp, "locker"), _pace(rp, "longrun")
    sw, iv, rt = _pace(rp, "schwelle"), _pace(rp, "intervall"), _pace(rp, "renntempo")
    texte = {
        "locker": f"{km:g} km locker, {_mmss(lo)}–{_mmss(lo + 25)}/km. Unterhaltung muss möglich sein.",
        "steig": f"{km:g} km locker ({_mmss(lo)}/km) plus 6 × 20 s Steigerung, dazwischen traben.",
        "longrun": f"{km:g} km ruhig, {_mmss(lr)}–{_mmss(lr + 20)}/km. Gleichmäßig, nicht schneller werden.",
        "longrun_rt": f"{km:g} km, davon die letzten 4 km im Renntempo {_mmss(rt)}/km.",
        "tempo3x5": f"Einlaufen 2 km, 3 × 5 min @ {_mmss(sw)}/km mit 2 min Trabpause, Auslaufen.",
        "tempo4x5": f"Einlaufen 2 km, 4 × 5 min @ {_mmss(sw)}/km mit 2 min Trabpause, Auslaufen.",
        "tempo2x6": f"Einlaufen 2 km, 2 × 6 min @ {_mmss(sw)}/km mit 3 min Trabpause, Auslaufen.",
        "int5x1000": f"Einlaufen 2 km, 5 × 1000 m @ {_mmss(iv)}/km mit 400 m Trabpause, Auslaufen.",
        "int6x1000": f"Einlaufen 2 km, 6 × 1000 m @ {_mmss(iv)}/km mit 400 m Trabpause, Auslaufen.",
        "schwelle2x15": f"Einlaufen 2 km, 2 × 15 min @ {_mmss(sw)}/km mit 3 min Trabpause, Auslaufen.",
        "rt3x2000": f"Einlaufen 2 km, 3 × 2000 m @ {_mmss(rt)}/km mit 3 min Trabpause, Auslaufen.",
        "rt2x2000": f"Einlaufen 2 km, 2 × 2000 m @ {_mmss(rt)}/km mit 3 min Trabpause, Auslaufen.",
        "rennen": f"Wettkampf {km:g} km. Zieltempo {_mmss(rt)}/km. Erste 3 km bewusst zurückhalten.",
    }
    return texte[key]


def _kind_for(name: str) -> str:
    if name in ("Tempo", "Intervall", "Schwelle", "Renntempo", "WETTKAMPF"):
        return KIND_QUALITY if name != "WETTKAMPF" else KIND_QUALITY
    if name in ("Longrun",):
        return KIND_LONG
    return KIND_EASY


def build_plan(race_date: date, race_pace_s: int) -> list[PlannedSession]:
    """13 Wochen rückwärts vom Renntag.

    Der Renntag muss ein Sonntag sein — die Vorlage legt die lange Einheit
    auf Sonntag, die Qualität auf Dienstag, die lockere auf Donnerstag.
    Fällt das Rennen auf einen anderen Tag, wird die Woche entsprechend
    verschoben, die Abstände bleiben gleich.
    """
    weeks = len(WEEKS_13)
    # Montag der Rennwoche
    race_week_monday = race_date - timedelta(days=race_date.weekday())
    first_monday = race_week_monday - timedelta(weeks=weeks - 1)

    out: list[PlannedSession] = []
    for w, (phase, di, do, so) in enumerate(WEEKS_13):
        monday = first_monday + timedelta(weeks=w)
        letzte_woche = w == weeks - 1
        for offset, (name, km, key) in ((1, di), (3, do), (6, so)):
            tag = monday + timedelta(days=offset)
            # In der Rennwoche liegt die Hauptbelastung auf dem Renntag selbst
            if letzte_woche and offset == 6:
                tag = race_date
            kind = _kind_for(name)
            out.append(
                PlannedSession(
                    day=tag,
                    kind=kind,
                    name=f"{name} {km:g} km" if name != "WETTKAMPF" else f"WETTKAMPF {km:g} km",
                    km=float(km),
                    load=round(km * LOAD_FACTOR[kind]),
                    description=_describe(key, km, race_pace_s),
                    week=w + 1,
                    phase=phase,
                )
            )
    return out


def summary(plan: list[PlannedSession]) -> list[dict]:
    """Wochenübersicht — für die Anzeige vor dem Schreiben."""
    per: dict[int, dict] = {}
    for s in plan:
        w = per.setdefault(
            s.week, {"woche": s.week, "phase": s.phase, "km": 0.0, "last": 0, "einheiten": []}
        )
        w["km"] += s.km
        w["last"] += s.load
        w["einheiten"].append(s.name)
    for w in per.values():
        w["km"] = round(w["km"], 1)
    return [per[k] for k in sorted(per)]
