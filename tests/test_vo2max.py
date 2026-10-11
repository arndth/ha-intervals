"""Tests der VO2max-Schätzung."""
from __future__ import annotations
import sys, types
from pathlib import Path
_C = Path(__file__).resolve().parents[1] / "custom_components" / "ha_intervals"
_p = types.ModuleType("ha_intervals"); _p.__path__=[str(_C)]; sys.modules.setdefault("ha_intervals", _p)
from ha_intervals.vo2max import estimate, rolling_best, series  # noqa: E402

HRMAX = 183


def test_bekannter_lauf():
    """10,2 km in 52:42 bei HF 167 — einer von Arndts echten Läufen."""
    v = estimate(10.2, 52 * 60 + 42, 167, HRMAX)
    assert v is not None
    assert 40 < v < 55, v


def test_hoehere_hfmax_senkt_den_wert():
    """Bei gleicher Leistung bedeutet eine höhere HFmax, dass man weiter vom
    Limit entfernt lief — die Hochrechnung fällt dann höher aus, nicht
    niedriger. Der Test hält die Richtung fest, damit ein Vorzeichenfehler
    auffällt."""
    tief = estimate(10.0, 3000, 160, 175)
    hoch = estimate(10.0, 3000, 160, 195)
    assert tief and hoch and hoch > tief, (tief, hoch)


def test_schneller_bei_gleicher_hf_ist_mehr():
    langsam = estimate(10.0, 3600, 160, HRMAX)
    schnell = estimate(10.0, 3000, 160, HRMAX)
    assert schnell > langsam


def test_ohne_hfmax_kein_wert():
    """Lieber nichts als eine Zahl ohne Grundlage — sie sähe aus wie eine echte."""
    assert estimate(10.0, 3000, 160, None) is None
    assert estimate(10.0, 3000, None, HRMAX) is None


def test_zu_kurz_oder_zu_langsam_wird_verworfen():
    assert estimate(1.1, 300, 171, HRMAX) is None      # 1,1 km
    assert estimate(5.0, 500, 160, HRMAX) is None      # unter 10 min
    assert estimate(10.0, 3000, 100, HRMAX) is None    # 55 % der HFmax
    assert estimate(10.0, 3000, 200, HRMAX) is None    # über der HFmax


def test_korrekturfaktor_skaliert():
    a = estimate(10.0, 3000, 160, HRMAX, 1.0)
    b = estimate(10.0, 3000, 160, HRMAX, 1.05)
    assert abs(b - a * 1.05) < 0.11


def test_unplausibles_ergebnis_wird_verworfen():
    # Absurd schnell: 10 km in 15 min bei niedriger HF
    assert estimate(10.0, 900, 130, HRMAX) is None


def test_series_laesst_untaugliche_laeufe_aus():
    akt = [
        {"id": "1", "day": "2026-05-01", "km": 10.0, "seconds": 3000, "hr_avg": 160},
        {"id": "2", "day": "2026-05-03", "km": 1.0, "seconds": 300, "hr_avg": 170},
        {"id": "3", "day": "2026-05-05", "km": 8.0, "seconds": 2500, "hr_avg": 155},
    ]
    s = series(akt, HRMAX)
    assert [x["activity_id"] for x in s] == ["1", "3"]
    assert [x["day"] for x in s] == ["2026-05-01", "2026-05-05"]


def test_rolling_best():
    v = [{"day": f"d{i}", "vo2max": x} for i, x in enumerate([44.0, 47.5, 45.1])]
    assert rolling_best(v) == 47.5
    assert rolling_best(v, fenster=1) == 45.1
    assert rolling_best([]) is None


if __name__ == "__main__":
    f = 0
    for n, fn in sorted(globals().items()):
        if not n.startswith("test_") or not callable(fn): continue
        try: fn(); print(f"  ok     {n}")
        except AssertionError as e: f += 1; print(f"  FEHLER {n}: {e}")
        except Exception as e: f += 1; print(f"  CRASH  {n}: {type(e).__name__}: {e}")
    print(f"\n{'ALLE TESTS BESTANDEN' if not f else f'{f} fehlgeschlagen'}")
    sys.exit(1 if f else 0)
