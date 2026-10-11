"""Regelwerk fürs Verschieben von Einheiten.

Bewusst **ohne** KI und ohne Home-Assistant-Abhängigkeiten: ein Training auf
morgen zu schieben ist kein Urteil, sondern eine Datumsänderung mit fünf
Randbedingungen. Ein Regelwerk antwortet sofort, kostet nichts, liefert bei
gleicher Eingabe dieselbe Antwort und lässt sich testen.

Die KI kommt erst dran, wenn hier *kein* zulässiger Zug mehr existiert — dann
ist es eine echte Trainingsfrage ("die Woche geht nicht mehr auf"), und genau
die gehört an ein Modell.

Das Modul ist rein: keine Importe aus `homeassistant`, damit es sich ohne
laufendes HA testen lässt.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from .const import (
    KIND_EASY,
    KIND_LONG,
    KIND_QUALITY,
    KIND_REST,
    MAX_WEEK_LOAD_DRIFT,
    MIN_REST_DAYS_PER_WEEK,
    MODE_DROP,
    MODE_PUSH,
    MODE_SWAP,
    QUALITY_KINDS,
    RACE_WEEK_DAYS,
)

_LOGGER = logging.getLogger(__name__)


# ── Datenmodell ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Session:
    """Eine geplante Einheit. `event_id` ist die intervals.icu-Event-ID."""

    event_id: str
    day: date
    kind: str
    name: str
    load: int = 0
    km: float = 0.0
    description: str = ""

    @property
    def is_quality(self) -> bool:
        return self.kind in QUALITY_KINDS

    @property
    def is_rest(self) -> bool:
        return self.kind == KIND_REST or self.load == 0


@dataclass(frozen=True)
class Change:
    """Eine Änderung, die nach intervals.icu geschrieben werden soll."""

    event_id: str
    action: str  # "move" | "delete"
    new_day: date | None = None


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str
    day: date | None = None


@dataclass(frozen=True)
class Alternative:
    mode: str
    target_day: date
    label: str


@dataclass
class MoveResult:
    """Ergebnis eines Zuges.

    `ok` heißt: die Änderungen werden geschrieben. `violations` steht nur bei
    Ablehnung. `notes` sind Hinweise zu einem *ausgeführten* Zug — etwa dass
    das Streichen die Wochenlast unter den Plan drückt.
    """

    ok: bool
    changes: list[Change] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    alternatives: list[Alternative] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    needs_replan: bool = False


# ── Hilfsmittel ──────────────────────────────────────────────────────────


def week_start(day: date) -> date:
    """Montag der Woche, in der `day` liegt."""
    return day - timedelta(days=day.weekday())


def _sessions_in_week(plan: list[Session], any_day: date) -> list[Session]:
    start = week_start(any_day)
    end = start + timedelta(days=6)
    return sorted(
        (s for s in plan if start <= s.day <= end), key=lambda s: s.day
    )


def _by_day(sessions: list[Session]) -> dict[date, list[Session]]:
    out: dict[date, list[Session]] = {}
    for s in sessions:
        out.setdefault(s.day, []).append(s)
    return out


# ── Die fünf Regeln ──────────────────────────────────────────────────────


def check_constraints(
    plan: list[Session],
    around: date,
    *,
    target_week_load: int | None = None,
) -> list[Violation]:
    """Prüft die Woche um `around` herum. Leere Liste = alles zulässig."""
    week = _sessions_in_week(plan, around)
    if not week:
        return []

    violations: list[Violation] = []
    per_day = _by_day(week)
    start = week_start(around)
    days = [start + timedelta(days=i) for i in range(7)]

    # 1 — keine zwei Qualitätseinheiten an aufeinanderfolgenden Tagen
    for i in range(len(days) - 1):
        a = any(s.is_quality for s in per_day.get(days[i], []))
        b = any(s.is_quality for s in per_day.get(days[i + 1], []))
        if a and b:
            violations.append(
                Violation(
                    "qualitaet_folgetag",
                    f"{days[i]:%a} und {days[i+1]:%a} sind beide harte Einheiten.",
                    days[i + 1],
                )
            )

    # 2 — keine Qualitätseinheit direkt vor dem Longrun
    for day, sessions in per_day.items():
        if not any(s.kind == KIND_LONG for s in sessions):
            continue
        before = per_day.get(day - timedelta(days=1), [])
        if any(s.kind == KIND_QUALITY for s in before):
            violations.append(
                Violation(
                    "qualitaet_vor_longrun",
                    f"Harte Einheit am {day - timedelta(days=1):%a} direkt vor dem Longrun.",
                    day,
                )
            )

    # 3 — mindestens ein Ruhetag pro Woche
    training_days = {d for d, ss in per_day.items() if any(not s.is_rest for s in ss)}
    rest_days = 7 - len(training_days)
    if rest_days < MIN_REST_DAYS_PER_WEEK:
        violations.append(
            Violation(
                "kein_ruhetag",
                f"{rest_days} Ruhetage in dieser Woche, mindestens "
                f"{MIN_REST_DAYS_PER_WEEK} nötig.",
            )
        )

    # 4 — Wochenlast innerhalb ±10 %
    if target_week_load:
        total = sum(s.load for s in week)
        drift = abs(total - target_week_load) / target_week_load
        if drift > MAX_WEEK_LOAD_DRIFT:
            violations.append(
                Violation(
                    "wochenlast",
                    f"Wochenlast {total} weicht {drift:.0%} von {target_week_load} ab.",
                )
            )

    # Hinweis: die Rennwochen-Regel steht bewusst **nicht** hier, sondern als
    # Wächter in `plan_move`. Sie beschreibt, was man tun darf, nicht ob der
    # Plan gültig ist — stünde sie hier, wäre jede Rennwoche dauerhaft
    # "verletzt" und selbst ein Streichen würde abgelehnt.

    return violations


# ── Züge ─────────────────────────────────────────────────────────────────


def _apply(plan: list[Session], changes: list[Change]) -> list[Session]:
    """Änderungen auf eine Kopie des Plans anwenden (für die Probe)."""
    moved = {c.event_id: c for c in changes}
    out: list[Session] = []
    for s in plan:
        c = moved.get(s.event_id)
        if c is None:
            out.append(s)
        elif c.action == "move" and c.new_day:
            out.append(replace(s, day=c.new_day))
        # "delete" fällt heraus
    return out


def _changes_for(
    plan: list[Session], session: Session, target: date, mode: str
) -> list[Change]:
    """Die reinen Änderungen eines Modus, noch ungeprüft."""
    if mode == MODE_DROP:
        return [Change(session.event_id, "delete")]

    if mode == MODE_SWAP:
        partners = [s for s in plan if s.day == target and s.event_id != session.event_id]
        changes = [Change(session.event_id, "move", target)]
        changes += [Change(p.event_id, "move", session.day) for p in partners]
        return changes

    if mode == MODE_PUSH:
        # Alles ab dem Zieltag rückt um einen Tag nach hinten, bis ein freier
        # Tag die Kette aufnimmt. Ohne diesen Stopp schöbe ein Zug die ganze
        # Saison.
        changes = [Change(session.event_id, "move", target)]
        others = [s for s in plan if s.event_id != session.event_id]
        # Nur echte Trainingstage blockieren. Ein Ruhetag nimmt die Kette auf —
        # sonst schiebt ein einziger Zug die gesamte Restsaison.
        busy = {s.day for s in others if not s.is_rest}
        day = target
        chain: list[Session] = []
        while day in busy:
            chain += [s for s in others if s.day == day and not s.is_rest]
            day += timedelta(days=1)
        for s in chain:
            changes.append(Change(s.event_id, "move", s.day + timedelta(days=1)))
        # Der Ruhetag, der die Kette aufnimmt, ist keiner mehr.
        for s in others:
            if s.day == day and s.is_rest:
                changes.append(Change(s.event_id, "delete"))
        return changes

    raise ValueError(f"Unbekannter Modus: {mode}")


def plan_move(
    plan: list[Session],
    event_id: str,
    target: date,
    mode: str,
    *,
    target_week_load: int | None = None,
    race_date: date | None = None,
) -> MoveResult:
    """Einen Zug planen und gegen die Regeln prüfen.

    Gibt bei Ablehnung die verletzten Regeln **und** die zulässigen
    Alternativen zurück, damit die Oberfläche sie als Knöpfe anbieten kann,
    statt den Nutzer raten zu lassen.
    """
    session = next((s for s in plan if s.event_id == str(event_id)), None)
    if session is None:
        return MoveResult(
            ok=False,
            violations=[Violation("unbekannt", f"Einheit {event_id} nicht im Plan.")],
        )

    if mode not in (MODE_SWAP, MODE_PUSH, MODE_DROP):
        return MoveResult(
            ok=False, violations=[Violation("modus", f"Unbekannter Modus: {mode}")]
        )

    # Rennwoche: nur streichen
    if (
        race_date
        and mode != MODE_DROP
        and 0 <= (race_date - week_start(session.day)).days < RACE_WEEK_DAYS
    ):
        return MoveResult(
            ok=False,
            violations=[
                Violation(
                    "rennwoche",
                    "In der Rennwoche wird nicht verschoben. Streichen ist möglich.",
                    session.day,
                )
            ],
            alternatives=[
                Alternative(MODE_DROP, session.day, "Einheit streichen")
            ],
        )

    changes = _changes_for(plan, session, target, mode)
    probe = _apply(plan, changes)

    # Streichen wird nie abgelehnt. Wer sagt "ich schaffe das heute nicht",
    # trainiert auch dann nicht, wenn das Regelwerk Nein sagt — eine Ablehnung
    # würde nur den Plan von der Wirklichkeit entkoppeln. Stattdessen wird der
    # Verlust gemeldet und gegebenenfalls eine Umplanung angestoßen.
    if mode == MODE_DROP:
        notes: list[str] = []
        replan = False
        for v in check_constraints(
            probe, session.day, target_week_load=target_week_load
        ):
            notes.append(v.message)
            if v.rule in ("wochenlast", "kein_ruhetag"):
                replan = True
        return MoveResult(ok=True, changes=changes, notes=notes, needs_replan=replan)

    violations = check_constraints(
        probe, session.day, target_week_load=target_week_load
    )
    if week_start(target) != week_start(session.day):
        violations += check_constraints(
            probe, target, target_week_load=target_week_load
        )

    if not violations:
        return MoveResult(ok=True, changes=changes)

    alternatives = _find_alternatives(
        plan, session, target_week_load=target_week_load, race_date=race_date
    )
    return MoveResult(
        ok=False,
        violations=violations,
        alternatives=alternatives,
        needs_replan=not alternatives,
    )


def _find_alternatives(
    plan: list[Session],
    session: Session,
    *,
    target_week_load: int | None,
    race_date: date | None,
    horizon_days: int = 7,
) -> list[Alternative]:
    """Alle zulässigen Einzelzüge im Horizont, am nächsten zuerst."""
    found: list[Alternative] = []
    for offset in range(1, horizon_days + 1):
        target = session.day + timedelta(days=offset)
        if race_date and 0 <= (race_date - week_start(target)).days < RACE_WEEK_DAYS:
            continue  # in die Rennwoche hinein wird nicht verschoben
        for mode in (MODE_SWAP, MODE_PUSH):
            changes = _changes_for(plan, session, target, mode)
            probe = _apply(plan, changes)
            bad = check_constraints(
                probe, session.day, target_week_load=target_week_load
            )
            if week_start(target) != week_start(session.day):
                bad += check_constraints(
                    probe, target, target_week_load=target_week_load
                )
            if bad:
                continue
            label = (
                f"Mit {target:%a} tauschen"
                if mode == MODE_SWAP
                else f"Auf {target:%a} schieben, Rest rückt nach"
            )
            found.append(Alternative(mode, target, label))

    # Streichen ist immer zulässig, steht aber zuletzt: es kostet Trainingsreiz.
    found.append(Alternative(MODE_DROP, session.day, "Einheit streichen"))
    return found


# ── Klassifizierung ──────────────────────────────────────────────────────


def classify(name: str, description: str, load: int, km: float) -> str:
    """Trainingsart aus dem intervals.icu-Eintrag ableiten.

    Grob und absichtlich konservativ: im Zweifel `locker`, damit das
    Regelwerk eher zu viel erlaubt als eine harte Einheit zu übersehen —
    das Gegenteil wäre der gefährlichere Fehler, aber auch der, der den
    Nutzer blockiert. Wer es genau will, trägt in intervals.icu eine
    Kategorie ein; die hat dann Vorrang.
    """
    # Markierungen und alles in eckigen Klammern entfernen. Sonst entscheidet
    # technischer Text über die Trainingsart — genau daran ist die erste
    # Fassung gescheitert.
    text = re.sub(r"\[[^\]]*\]", " ", f"{name} {description}").lower()
    if load == 0:
        return KIND_REST
    if any(w in text for w in ("long", "lang", "dauerlauf lang")):
        return KIND_LONG
    if km >= 15:
        return KIND_LONG
    if any(
        w in text
        for w in (
            "interval",
            "tempo",
            "schwelle",
            "threshold",
            "fahrtspiel",
            "wettkampf",
            "vo2",
            "pyramide",
            "berg",
        )
    ):
        return KIND_QUALITY
    return KIND_EASY
