"""Tests für die Datumserkennung.

Hintergrund: in v0.1.0 nahm der Config-Flow das Renndatum als freien Text
entgegen und der Koordinator las es mit `date.fromisoformat`. Eine deutsche
Eingabe (`10.01.2026`) beendete daraufhin `daten_abfragen` mit HTTP 500 und
verhinderte das Anlegen von `sensor.tage_bis_zum_rennen`.

    python3 tests/test_util.py
"""

from __future__ import annotations

import sys
import types
from datetime import date, datetime
from pathlib import Path

_COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "ha_intervals"
_pkg = types.ModuleType("ha_intervals")
_pkg.__path__ = [str(_COMPONENT)]
sys.modules.setdefault("ha_intervals", _pkg)

from ha_intervals.util import extract_syntax, parse_date, to_iso  # noqa: E402


def test_iso():
    assert parse_date("2027-01-10") == date(2027, 1, 10)


def test_deutsch():
    """Der Fall, der v0.1.0 zum Absturz brachte."""
    assert parse_date("10.01.2026") == date(2026, 1, 10)
    assert parse_date("1.2.2027") == date(2027, 2, 1)
    assert parse_date("10.01.26") == date(2026, 1, 10)


def test_zeitstempel():
    assert parse_date("2027-01-10T00:00:00") == date(2027, 1, 10)


def test_date_objekte():
    assert parse_date(date(2027, 1, 10)) == date(2027, 1, 10)
    assert parse_date(datetime(2027, 1, 10, 7, 30)) == date(2027, 1, 10)


def test_unlesbares_gibt_none_statt_ausnahme():
    """Entscheidend: nie eine Ausnahme — sonst stirbt wieder ein Dienst."""
    for schrott in ("morgen", "", None, "2027-13-45", "abc", 17, "10/01/2026"):
        assert parse_date(schrott) is None, schrott


def test_mehrdeutiges_wird_abgelehnt():
    """01/10/2026 kann Januar oder Oktober heißen. Lieber nachfragen als raten."""
    assert parse_date("01/10/2026") is None


def test_to_iso():
    assert to_iso("10.01.2026") == "2026-01-10"
    assert to_iso("2027-01-10") == "2027-01-10"
    assert to_iso("quatsch") is None


def test_extract_syntax_hin_und_zurueck():
    """Was der Generator schreibt, muss unverändert zurückkommen — sonst
    exportieren wir etwas anderes, als in intervals.icu steht."""
    syntax = "- 2km Z2 Pace\n\n5x\n- 1km Z5 Pace\n- 0.4km Z1 Pace\n\n- 1.5km Z2 Pace"
    beschreibung = (
        syntax
        + "\n\nEinlaufen 2 km, 5 × 1000 m @ 4:24/km mit 400 m Trabpause, Auslaufen."
        + "\n\n[HA-LAUFPLAN] art=qualitaet km=11.5 woche=7 phase=Entwicklung"
    )
    assert extract_syntax(beschreibung) == syntax


def test_extract_syntax_ignoriert_prosa_und_markierung():
    assert extract_syntax("Nur Prosa, kein Workout.") == ""
    assert extract_syntax("[HA-LAUFPLAN] art=locker km=5") == ""
    assert extract_syntax("") == ""
    assert extract_syntax(None) == ""


def test_extract_syntax_behaelt_wiederholungskoepfe():
    assert extract_syntax("6x\n- 20s Z5 Pace\n- 60s Z1 Pace") == (
        "6x\n- 20s Z5 Pace\n- 60s Z1 Pace")


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
