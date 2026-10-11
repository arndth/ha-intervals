"""Kleine Helfer ohne Home-Assistant-Abhängigkeiten."""

from __future__ import annotations

from datetime import date, datetime

# Reihenfolge ist Absicht: ISO zuerst, dann die deutschen Schreibweisen.
# Keine Formate mit mehrdeutiger Reihenfolge (etwa 01/10/2026) — dort wäre
# nicht entscheidbar, ob Januar oder Oktober gemeint ist, und ein stilles
# Fehlraten ist schlimmer als eine Rückfrage.
_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%Y/%m/%d")


def parse_date(value: object) -> date | None:
    """Ein Datum aus verschiedenen Schreibweisen lesen.

    Gibt `None` zurück, wenn nichts passt — nie eine Ausnahme. Ein falsch
    getipptes Renndatum darf keine Entität am Anlegen hindern und keinen
    Dienst mit 500 beenden; genau das ist in v0.1.0 passiert.
    """
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()

    text = str(value).strip()
    for f in _FORMATS:
        try:
            return datetime.strptime(text, f).date()
        except ValueError:
            continue

    # Zeitstempel wie "2027-01-10T00:00:00" mitnehmen
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def to_iso(value: object) -> str | None:
    """Beliebige Schreibweise → `JJJJ-MM-TT`, oder None."""
    d = parse_date(value)
    return d.isoformat() if d else None


def extract_syntax(description: str) -> str:
    """Workout-Schreibweise aus einer Beschreibung herauslösen.

    Geparst werden von intervals.icu wie vom n8n-Konverter nur Zeilen, die
    mit "-" beginnen, sowie Wiederholungsköpfe wie "5x". Alles andere —
    Prosa, Markierung — ist für beide unsichtbar. Dieselbe Regel gilt hier
    beim Zurücklesen.
    """
    import re as _re

    out: list[str] = []
    for zeile in (description or "").splitlines():
        z = zeile.strip()
        if z.startswith("-") or _re.fullmatch(r"\d+x", z, _re.I):
            out.append(z)
        elif not z and out:
            out.append("")          # Leerzeile trennt Wiederholungsblöcke
    # führende und doppelte Leerzeilen am Ende entfernen
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)
