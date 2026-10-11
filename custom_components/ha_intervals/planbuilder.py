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
    syntax: str = ""          # intervals.icu-Workout-Schreibweise


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


def _describe(key: str, km: float, rp: int, easy: int | None = None) -> str:
    """Beschreibungstext mit konkreten Tempovorgaben.

    `rp` steuert die harten Einheiten (vom Ziel her), `easy` die lockeren
    (vom heutigen Dauerlauftempo her). Beides aus dem Ziel abzuleiten war
    falsch: lockeres Laufen richtet sich nach der aktuellen aeroben Form,
    nicht nach dem, was man im Januar laufen will. In der ersten Fassung
    standen dadurch 6:21/km als "locker" bei einem Läufer, der seine
    Dauerläufe gewohnheitsmäßig um 5:15/km läuft — eine Vorgabe, die man
    schlicht ignoriert.
    """
    lo = easy or _pace(rp, "locker")
    # Lockerer Lauf und langer Lauf liegen im selben aeroben Bereich; der
    # Unterschied ist die Dauer, nicht das Tempo. Eine eigene, schnellere
    # Longrun-Pace anzusetzen wäre die alte Lehre und würde den langen Lauf
    # zur zweiten Qualitätseinheit machen — bei drei Einheiten pro Woche
    # wäre das eine zu viel.
    lr = lo if easy else _pace(rp, "longrun")
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


# ── intervals.icu-Workout-Schreibweise ──────────────────────────────────
#
# Daraus macht intervals.icu einen *strukturierten* Workout statt nur eines
# Textes — die Uhr zählt die Intervalle dann selbst herunter. Dieselbe
# Schreibweise versteht der n8n-Konverter, der nach TrainingPeaks schiebt.
#
# Drei Fallen, alle aus dem Parser gelesen und nicht geraten:
#   · `m` heißt **Minuten**, nicht Meter. 400 m Trabpause ist `0.4km`.
#   · Eine Leerzeile beendet einen Wiederholungsblock. Ohne sie saugt er
#     das Auslaufen mit hinein.
#   · Der *erste* Schritt legt den Zieltyp für den ganzen Workout fest —
#     deshalb trägt jede erste Zeile „Pace".

Z_RECOVERY, Z_EASY, Z_THRESHOLD, Z_VO2 = "Z1", "Z2", "Z4", "Z5"


def _rep(reps: int, arbeit: str, pause: str) -> str:
    return f"{reps}x\n- {arbeit}\n- {pause}"


def _syntax(key: str, km: float) -> str:
    """Workout-Schreibweise zu einem Beschreibungsschlüssel."""
    ein = f"- 2km {Z_EASY} Pace"
    aus = f"- 1.5km {Z_EASY} Pace"

    if key in ("locker", "longrun"):
        return f"- {km:g}km {Z_EASY} Pace"
    if key == "longrun_rt":
        return f"- {max(km - 4, 1):g}km {Z_EASY} Pace\n\n- 4km {Z_THRESHOLD} Pace"
    if key == "steig":
        return (
            f"- {max(km - 1.5, 1):g}km {Z_EASY} Pace\n\n"
            + _rep(6, f"20s {Z_VO2} Pace", f"60s {Z_RECOVERY} Pace")
        )
    if key == "rennen":
        return f"- {km:g}km {Z_THRESHOLD} Pace"

    blocks = {
        "tempo3x5": _rep(3, f"5m {Z_THRESHOLD} Pace", f"2m {Z_RECOVERY} Pace"),
        "tempo4x5": _rep(4, f"5m {Z_THRESHOLD} Pace", f"2m {Z_RECOVERY} Pace"),
        "tempo2x6": _rep(2, f"6m {Z_THRESHOLD} Pace", f"3m {Z_RECOVERY} Pace"),
        "schwelle2x15": _rep(2, f"15m {Z_THRESHOLD} Pace", f"3m {Z_RECOVERY} Pace"),
        "int5x1000": _rep(5, f"1km {Z_VO2} Pace", f"0.4km {Z_RECOVERY} Pace"),
        "int6x1000": _rep(6, f"1km {Z_VO2} Pace", f"0.4km {Z_RECOVERY} Pace"),
        "rt3x2000": _rep(3, f"2km {Z_THRESHOLD} Pace", f"3m {Z_RECOVERY} Pace"),
        "rt2x2000": _rep(2, f"2km {Z_THRESHOLD} Pace", f"3m {Z_RECOVERY} Pace"),
    }
    if key in blocks:
        return f"{ein}\n\n{blocks[key]}\n\n{aus}"
    return f"- {km:g}km {Z_EASY} Pace"


def _kind_for(name: str) -> str:
    if name in ("Tempo", "Intervall", "Schwelle", "Renntempo", "WETTKAMPF"):
        return KIND_QUALITY if name != "WETTKAMPF" else KIND_QUALITY
    if name in ("Longrun",):
        return KIND_LONG
    return KIND_EASY


def _week_pace(week: int, weeks: int, start_s: int, goal_s: int) -> int:
    """Bezugstempo der Woche.

    Die Vorgaben einer Einheit richten sich nach dem Leistungsstand, den man
    *in dieser Woche* hat — nicht nach dem, den man am Renntag haben will.
    Sonst stehen in Woche 7 Intervalle, die schneller sind als das aktuelle
    Wettkampftempo: unausführbar, und die Einheit verfehlt ihren Zweck.

    Deshalb wandert das Bezugstempo von `start_s` zum Ziel und erreicht es in
    der Schärfungsphase (etwa 80 % der Planlänge). Die letzten Wochen laufen
    dann tatsächlich im Zieltempo — da muss es sitzen.
    """
    if start_s is None or start_s <= goal_s:
        return goal_s
    ziel_ab = max(1, int(weeks * 0.8))
    if week >= ziel_ab:
        return goal_s
    anteil = (week - 1) / max(1, ziel_ab - 1)
    return round(start_s + (goal_s - start_s) * anteil)


def scale_template(scale: float, max_long_km: float) -> list:
    """Wochenvorlage auf den Umfang des Läufers strecken.

    Die Vorlage ist für einen Wiedereinsteiger mit 5-km-Läufen geschrieben.
    Wer 10 km gewohnt ist, bekommt sie entsprechend gestreckt — der lange
    Lauf aber gedeckelt, weil er sonst über das Dreifache der Renndistanz
    hinauswächst und mehr kostet als er bringt.
    """
    out = []
    for phase, di, do, so in WEEKS_13:
        def skaliert(e, lang=False):
            name, km, key = e
            if key == "rennen":
                return e                      # Renndistanz bleibt, was sie ist
            neu = km * scale
            if lang:
                neu = min(neu, max_long_km)
            return (name, round(neu * 2) / 2, key)   # auf halbe km runden
        out.append((phase, skaliert(di), skaliert(do), skaliert(so, lang=True)))
    return out


def build_plan(
    race_date: date,
    race_pace_s: int,
    start_pace_s: int | None = None,
    easy_pace_s: int | None = None,
    scale: float = 1.0,
    max_long_km: float = 16.0,
) -> list[PlannedSession]:
    """13 Wochen rückwärts vom Renntag.

    Der Renntag muss ein Sonntag sein — die Vorlage legt die lange Einheit
    auf Sonntag, die Qualität auf Dienstag, die lockere auf Donnerstag.
    Fällt das Rennen auf einen anderen Tag, wird die Woche entsprechend
    verschoben, die Abstände bleiben gleich.
    """
    vorlage = scale_template(scale, max_long_km) if scale != 1.0 else WEEKS_13
    weeks = len(vorlage)
    # Montag der Rennwoche
    race_week_monday = race_date - timedelta(days=race_date.weekday())
    first_monday = race_week_monday - timedelta(weeks=weeks - 1)

    out: list[PlannedSession] = []
    for w, (phase, di, do, so) in enumerate(vorlage):
        monday = first_monday + timedelta(weeks=w)
        letzte_woche = w == weeks - 1
        for offset, (name, km, key) in ((1, di), (3, do), (6, so)):
            tag = monday + timedelta(days=offset)
            # In der Rennwoche liegt die Hauptbelastung auf dem Renntag selbst
            if letzte_woche and offset == 6:
                tag = race_date
            kind = _kind_for(name)
            # Der Wettkampf selbst läuft immer im Zieltempo, egal wo die
            # Progression gerade steht.
            bezug = (
                race_pace_s
                if key == "rennen"
                else _week_pace(w + 1, weeks, start_pace_s, race_pace_s)
            )
            out.append(
                PlannedSession(
                    day=tag,
                    kind=kind,
                    name=f"{name} {km:g} km" if name != "WETTKAMPF" else f"WETTKAMPF {km:g} km",
                    km=float(km),
                    load=round(km * LOAD_FACTOR[kind]),
                    description=_describe(key, km, bezug, easy_pace_s),
                    syntax=_syntax(key, km),
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
