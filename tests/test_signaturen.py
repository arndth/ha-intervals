"""Statische Prüfung der Datenklassen-Aufrufe.

Hintergrund: in v0.3.0 bekam `planbuilder.PlannedSession` ein Feld `syntax`.
Der Koordinator baut daraus auch `planner.Session` — dort fehlte das Feld,
und die Integration stürzte beim Start ab:

    Session.__init__() got an unexpected keyword argument 'syntax'

Die übrigen Testdateien erreichen den Koordinator nicht, weil er Home
Assistant importiert. Dieser Test braucht ihn nicht auszuführen: er liest
den Quelltext und vergleicht jeden Aufruf einer Datenklasse mit deren
Feldern. Damit fällt diese Fehlerklasse in der CI auf, nicht erst beim
Nutzer.

    python3 tests/test_signaturen.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "ha_intervals"


def _dataclass_fields() -> dict[str, set[str]]:
    """Felder aller Datenklassen im Paket."""
    felder: dict[str, set[str]] = {}
    for datei in COMPONENT.glob("*.py"):
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.ClassDef):
                continue
            ist_datenklasse = any(
                (isinstance(d, ast.Name) and d.id == "dataclass")
                or (isinstance(d, ast.Call) and getattr(d.func, "id", "") == "dataclass")
                for d in knoten.decorator_list
            )
            if ist_datenklasse:
                felder[knoten.name] = {
                    k.target.id
                    for k in knoten.body
                    if isinstance(k, ast.AnnAssign) and isinstance(k.target, ast.Name)
                }
    return felder


def test_keine_unbekannten_schluesselwortargumente():
    felder = _dataclass_fields()
    assert felder, "keine Datenklassen gefunden — Prüfung liefe ins Leere"

    probleme: list[str] = []
    for datei in COMPONENT.glob("*.py"):
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        for knoten in ast.walk(baum):
            if (
                isinstance(knoten, ast.Call)
                and isinstance(knoten.func, ast.Name)
                and knoten.func.id in felder
            ):
                benutzt = {k.arg for k in knoten.keywords if k.arg}
                unbekannt = benutzt - felder[knoten.func.id]
                if unbekannt:
                    probleme.append(
                        f"{datei.name}:{knoten.lineno} {knoten.func.id}(…) "
                        f"kennt {sorted(unbekannt)} nicht"
                    )
    assert not probleme, "\n  " + "\n  ".join(probleme)


def test_session_und_plannedsession_teilen_die_gemeinsamen_felder():
    """Der Koordinator schreibt zwischen beiden hin und her. Was in der einen
    steht und von der anderen gelesen wird, muss in beiden existieren."""
    f = _dataclass_fields()
    gemeinsam = {"day", "kind", "name", "km", "load", "description", "syntax"}
    for klasse in ("Session", "PlannedSession"):
        fehlend = gemeinsam - f.get(klasse, set())
        assert not fehlend, f"{klasse} fehlt: {sorted(fehlend)}"


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
    print(f"\n{'ALLE TESTS BESTANDEN' if not fehler else f'{fehler} fehlgeschlagen'}")
    sys.exit(1 if fehler else 0)
