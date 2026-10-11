"""Tests für den Plangenerator."""

from __future__ import annotations

import sys
import types
from datetime import date, timedelta
from pathlib import Path

_COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "ha_intervals"
_pkg = types.ModuleType("ha_intervals")
_pkg.__path__ = [str(_COMPONENT)]
sys.modules.setdefault("ha_intervals", _pkg)

from ha_intervals.const import KIND_EASY, KIND_LONG, KIND_QUALITY  # noqa: E402
from ha_intervals.planbuilder import build_plan, summary  # noqa: E402

RENNEN = date(2027, 1, 10)   # Sonntag
PACE = 300                   # 5:00/km


def plan():
    return build_plan(RENNEN, PACE)


def test_dreizehn_wochen_je_drei_einheiten():
    p = plan()
    assert len(p) == 39, len(p)
    assert {s.week for s in p} == set(range(1, 14))
    for w in range(1, 14):
        assert len([s for s in p if s.week == w]) == 3


def test_endet_am_renntag():
    p = plan()
    letzte = max(p, key=lambda s: s.day)
    assert letzte.day == RENNEN
    assert "WETTKAMPF" in letzte.name


def test_startet_montags_dreizehn_wochen_vorher():
    p = plan()
    erste = min(p, key=lambda s: s.day)
    assert erste.day == date(2026, 10, 13)      # Dienstag der ersten Woche
    assert (RENNEN - erste.day).days == 89


def test_keine_qualitaet_im_wiederaufbau():
    """Nach fünf Wochen Pause ist Tempoarbeit in Woche 1 ein Verletzungsrisiko."""
    for s in plan():
        if s.phase == "Wiederaufbau":
            assert s.kind != KIND_QUALITY, (s.week, s.name)


def test_wochentage_sind_di_do_so():
    for s in plan():
        assert s.day.weekday() in (1, 3, 6), (s.day, s.name)


def test_keine_zwei_harten_tage_hintereinander():
    p = sorted(plan(), key=lambda s: s.day)
    for a, b in zip(p, p[1:]):
        if (b.day - a.day).days == 1:
            assert not (a.kind == KIND_QUALITY and b.kind == KIND_QUALITY)


def test_longrun_waechst_und_bleibt_unter_der_renndistanz():
    lang = [s for s in plan() if s.kind == KIND_LONG]
    assert lang, "keine Longruns"
    assert max(s.km for s in lang) == 16
    # Der längste Longrun liegt über der Renndistanz von 13 km — gewollt,
    # damit die Distanz im Rennen nie das Problem ist.
    assert max(s.km for s in lang) > 13


def test_volumen_steigt_und_hat_entlastungswochen():
    wo = summary(plan())
    km = [w["km"] for w in wo]
    assert km[0] < km[8], "Volumen muss über den Aufbau steigen"
    # Woche 4, 8 und 12 sind Entlastung: leichter als die Woche davor
    for i in (3, 7, 11):
        assert km[i] < km[i - 1], (i + 1, km[i], km[i - 1])
    assert km[-1] < km[-2], "Taperwoche muss leichter sein"


def test_tempovorgaben_stehen_in_der_beschreibung():
    p = plan()
    renntempo = [s for s in p if "Renntempo" in s.name]
    assert renntempo
    assert "5:00" in renntempo[0].description
    locker = [s for s in p if s.kind == KIND_EASY][0]
    assert "6:06" in locker.description or "6:0" in locker.description


def test_last_ist_gesetzt():
    assert all(s.load > 0 for s in plan())


def test_andere_pace_verschiebt_alle_vorgaben():
    schnell = build_plan(RENNEN, 270)   # 4:30/km
    rt = [s for s in schnell if "Renntempo" in s.name][0]
    assert "4:30" in rt.description


def test_progression_startet_beim_heutigen_stand():
    """Ohne Progression stünden in Woche 7 Intervalle schneller als das
    aktuelle Wettkampftempo — unausführbar."""
    p = build_plan(RENNEN, 270, start_pace_s=312)   # Ziel 4:30, heute 5:12
    w1 = [s for s in p if s.week == 1 and s.kind == KIND_EASY][0]
    w13 = [s for s in p if s.week == 13 and "WETTKAMPF" in s.name][0]
    assert "6:21" in w1.description, w1.description   # 312 × 1,22
    assert "4:30" in w13.description, w13.description


def test_progression_erreicht_das_ziel_vor_dem_rennen():
    p = build_plan(RENNEN, 270, start_pace_s=312)
    rt = [s for s in p if "Renntempo" in s.name]
    assert rt, "keine Renntempo-Einheiten"
    # Die Renntempo-Einheiten liegen in den Wochen 11 und 12, also nach dem
    # Umschaltpunkt bei 80 % der Planlänge.
    for s in rt:
        assert "4:30" in s.description, (s.week, s.description)


def test_ohne_startpace_bleibt_alles_beim_ziel():
    a = build_plan(RENNEN, PACE)
    b = build_plan(RENNEN, PACE, start_pace_s=None)
    assert [x.description for x in a] == [x.description for x in b]


def test_schnellerer_start_als_ziel_wird_ignoriert():
    """Wer schon schneller ist als sein Ziel, trainiert nicht langsamer."""
    p = build_plan(RENNEN, 300, start_pace_s=270)
    w1 = [s for s in p if s.week == 1 and s.kind == KIND_EASY][0]
    assert "6:06" in w1.description   # 300 × 1,22, also Zielbezug


def test_skalierung_hebt_den_umfang():
    """Wer 10 km gewohnt ist, startet nicht mit 5-km-Läufen."""
    klein = summary(build_plan(RENNEN, PACE))
    gross = summary(build_plan(RENNEN, PACE, scale=1.45, max_long_km=19.5))
    assert gross[0]["km"] > klein[0]["km"] * 1.3
    assert max(w["km"] for w in gross) > max(w["km"] for w in klein) * 1.25


def test_langer_lauf_wird_gedeckelt():
    p = build_plan(RENNEN, PACE, scale=2.0, max_long_km=19.5)
    lang = [s for s in p if s.kind == KIND_LONG]
    assert max(s.km for s in lang) <= 19.5


def test_renndistanz_bleibt_unskaliert():
    p = build_plan(RENNEN, PACE, scale=1.45, max_long_km=19.5)
    rennen = [s for s in p if "WETTKAMPF" in s.name][0]
    assert rennen.km == 13.0


def test_lockertempo_folgt_dem_dauerlauftempo_nicht_dem_ziel():
    """Der Kern des Fehlers: lockere Läufe richten sich nach der heutigen
    aeroben Form, nicht nach der Zielzeit im Januar."""
    ohne = build_plan(RENNEN, 270, start_pace_s=294)
    mit = build_plan(RENNEN, 270, start_pace_s=294, easy_pace_s=330)  # 5:30
    e_ohne = [s for s in ohne if s.kind == KIND_EASY][0].description
    e_mit = [s for s in mit if s.kind == KIND_EASY][0].description
    assert "5:59" in e_ohne, e_ohne          # 294 × 1,22 = 358,7 s
    assert "5:30" in e_mit, e_mit
    # Die harten Einheiten bleiben vom Ziel bestimmt
    q = [s for s in mit if "Renntempo" in s.name][0]
    assert "4:30" in q.description


def test_summary():
    wo = summary(plan())
    assert len(wo) == 13
    assert wo[0]["phase"] == "Wiederaufbau"
    assert wo[-1]["phase"] == "Taper"
    assert sum(w["km"] for w in wo) == sum(s.km for s in plan())


if __name__ == "__main__":
    fehler = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn(); print(f"  ok     {name}")
        except AssertionError as e:
            fehler += 1; print(f"  FEHLER {name}: {e}")
        except Exception as e:  # noqa: BLE001
            fehler += 1; print(f"  CRASH  {name}: {type(e).__name__}: {e}")
    print(f"\n{'ALLE TESTS BESTANDEN' if not fehler else f'{fehler} fehlgeschlagen'}")
    sys.exit(1 if fehler else 0)
