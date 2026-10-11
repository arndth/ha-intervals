"""Tests fürs Regelwerk. Laufen ohne Home Assistant:

    python3 -m pytest tests/ -q
    python3 tests/test_planner.py        # auch ohne pytest
"""

from __future__ import annotations

import sys
import types
from datetime import date, timedelta
from pathlib import Path

# planner.py ist absichtlich frei von Home-Assistant-Importen, das Paket-
# __init__.py daneben ist es nicht. Deshalb wird hier ein leeres Paket mit
# passendem __path__ vorab in sys.modules gelegt: relative Importe
# (`from .const import ...`) lösen damit auf, ohne dass die Integration
# selbst hochfährt. So laufen die Tests ohne installiertes Home Assistant.
_COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "ha_intervals"
_pkg = types.ModuleType("ha_intervals")
_pkg.__path__ = [str(_COMPONENT)]
sys.modules.setdefault("ha_intervals", _pkg)

from ha_intervals.const import (  # noqa: E402
    KIND_EASY,
    KIND_LONG,
    KIND_QUALITY,
    KIND_REST,
    MODE_DROP,
    MODE_PUSH,
    MODE_SWAP,
)
from ha_intervals.planner import (  # noqa: E402
    Change,
    Session,
    check_constraints,
    classify,
    plan_move,
    week_start,
)

# Montag, 12. Oktober 2026
MO = date(2026, 10, 12)
D = lambda n: MO + timedelta(days=n)  # noqa: E731


def woche() -> list[Session]:
    """Die Beispielwoche: Mo Ruhe, Di Intervall, Mi/Do/Sa locker, So Longrun."""
    return [
        Session("1", D(0), KIND_REST, "Ruhe", 0, 0),
        Session("2", D(1), KIND_QUALITY, "5 × 1000 m", 92, 11),
        Session("3", D(2), KIND_EASY, "8 km locker", 46, 8),
        Session("4", D(3), KIND_EASY, "10 km locker", 58, 10),
        Session("5", D(4), KIND_REST, "Ruhe", 0, 0),
        Session("6", D(5), KIND_EASY, "10 km locker", 55, 10),
        Session("7", D(6), KIND_LONG, "16 km Longrun", 104, 16),
    ]


def test_ausgangsplan_ist_zulaessig():
    assert check_constraints(woche(), MO, target_week_load=355) == []


def test_tauschen_mittwoch_donnerstag_ist_erlaubt():
    r = plan_move(woche(), "3", D(3), MODE_SWAP, target_week_load=355)
    assert r.ok, [v.message for v in r.violations]
    bewegt = {(c.event_id, c.new_day) for c in r.changes}
    assert ("3", D(3)) in bewegt and ("4", D(2)) in bewegt


def test_intervall_auf_samstag_kollidiert_mit_longrun():
    """Di-Intervall auf Sa → direkt vor dem So-Longrun. Muss abgelehnt werden."""
    r = plan_move(woche(), "2", D(5), MODE_SWAP, target_week_load=355)
    assert not r.ok
    assert any(v.rule == "qualitaet_vor_longrun" for v in r.violations), [
        v.rule for v in r.violations
    ]
    assert r.alternatives, "Bei Ablehnung müssen Alternativen angeboten werden"


def test_zwei_harte_einheiten_hintereinander_werden_erkannt():
    plan = woche()
    plan[2] = Session("3", D(2), KIND_QUALITY, "Tempo", 90, 10)  # Mi hart
    assert any(v.rule == "qualitaet_folgetag" for v in check_constraints(plan, MO))


def test_ruhetag_bleibt_erhalten():
    plan = [s for s in woche() if s.kind != KIND_REST]
    plan += [
        Session("8", D(0), KIND_EASY, "6 km", 35, 6),
        Session("9", D(4), KIND_EASY, "6 km", 35, 6),
    ]
    assert any(v.rule == "kein_ruhetag" for v in check_constraints(plan, MO))


def test_streichen_ist_immer_moeglich():
    r = plan_move(woche(), "2", D(1), MODE_DROP, target_week_load=355)
    assert r.ok
    assert r.changes == [Change("2", "delete", None)]


def test_schieben_laesst_kette_nachruecken():
    """Mi → Do: Do ist belegt, rückt auf Fr (frei). Danach ist Schluss."""
    r = plan_move(woche(), "3", D(3), MODE_PUSH, target_week_load=355)
    ziele = {c.event_id: c.new_day for c in r.changes}
    assert ziele["3"] == D(3)
    assert ziele["4"] == D(4)
    assert "6" not in ziele, "Die Kette darf am freien Tag stoppen"


def test_rennwoche_erlaubt_nur_streichen():
    renntag = D(6)
    r = plan_move(woche(), "3", D(3), MODE_SWAP, race_date=renntag)
    assert not r.ok
    assert any(v.rule == "rennwoche" for v in r.violations)
    assert [a.mode for a in r.alternatives] == [MODE_DROP]

    r2 = plan_move(woche(), "3", D(2), MODE_DROP, race_date=renntag)
    assert r2.ok


def test_wochenlast_grenze():
    # Streichen der harten Einheit nimmt 92 von 355 — das sind 26 %.
    r = plan_move(woche(), "2", D(1), MODE_SWAP, target_week_load=355)
    assert r.ok  # Tauschen ändert die Last nicht
    verbleibend = [s for s in woche() if s.event_id != "2"]
    assert any(
        v.rule == "wochenlast"
        for v in check_constraints(verbleibend, MO, target_week_load=355)
    )


def test_unbekannte_einheit():
    r = plan_move(woche(), "999", D(3), MODE_SWAP)
    assert not r.ok and r.violations[0].rule == "unbekannt"


def test_markierung_verfaelscht_die_art_nicht():
    """Die erste Markierung hieß "[ha_intervals]" — und enthält damit die
    Zeichenfolge "interval". Der Klassifizierer stufte daraufhin jede
    Einheit als Qualitätstraining ein, auch "Locker 5 km". Technischer Text
    in Klammern darf die Trainingsart nie bestimmen."""
    for marker in ("[ha_intervals] Woche 1", "[HA-LAUFPLAN] art=locker km=5", ""):
        art = classify("Locker 5 km", f"5 km locker, 6:21/km.\n\n{marker}", 30, 5.0)
        assert art == KIND_EASY, (marker, art)
    # Echte Qualität wird weiterhin erkannt
    assert classify("Intervall 8 km", "5 × 1000 m @ 4:24/km", 68, 8.0) == KIND_QUALITY


def test_week_start():
    assert week_start(D(6)) == MO
    assert week_start(MO) == MO


def test_classify():
    assert classify("Ruhe", "", 0, 0) == KIND_REST
    assert classify("5 × 1000 m", "Intervall", 92, 11) == KIND_QUALITY
    assert classify("Longrun", "16 km", 104, 16) == KIND_LONG
    assert classify("Dauerlauf", "8 km locker", 46, 8) == KIND_EASY
    # 15 km gelten auch ohne Schlüsselwort als Longrun
    assert classify("Dauerlauf", "", 90, 15) == KIND_LONG


if __name__ == "__main__":
    fehler = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"  ok     {name}")
        except AssertionError as e:
            fehler += 1
            print(f"  FEHLER {name}: {e}")
        except Exception as e:  # noqa: BLE001
            fehler += 1
            print(f"  CRASH  {name}: {type(e).__name__}: {e}")
    print(f"\n{'ALLE TESTS BESTANDEN' if not fehler else f'{fehler} Test(s) fehlgeschlagen'}")
    sys.exit(1 if fehler else 0)
