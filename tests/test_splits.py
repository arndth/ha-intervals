"""Tests für die Kilometer-Splits."""
from __future__ import annotations
import sys, types
from pathlib import Path
_C = Path(__file__).resolve().parents[1] / "custom_components" / "ha_intervals"
_p = types.ModuleType("ha_intervals"); _p.__path__=[str(_C)]; sys.modules.setdefault("ha_intervals", _p)
from ha_intervals.analysis import compute_splits  # noqa: E402


def lauf(km_paces, hf=150):
    """Streams bauen: je Kilometer eine Pace in Sekunden."""
    d, t, h = [0.0], [0], [hf]
    for i, pace in enumerate(km_paces):
        for sek in range(1, pace + 1):
            d.append(i * 1000 + sek / pace * 1000)
            t.append(t[-1] + 1)
            h.append(hf)
    return {"distance": d, "time": t, "heartrate": h}


def test_drei_gleiche_kilometer():
    s = compute_splits(lauf([300, 300, 300]))
    assert len(s) == 3, s
    assert all(x["sekunden"] == 300 for x in s)
    assert all(not x["teil"] for x in s)
    assert [x["km"] for x in s] == [1, 2, 3]


def test_unterschiedliche_paces():
    s = compute_splits(lauf([300, 270, 330]))
    assert [x["sekunden"] for x in s] == [300, 270, 330]


def test_angebrochener_kilometer_wird_gekennzeichnet():
    st = lauf([300, 300])
    # 400 m anhängen in 2:00
    for sek in range(1, 121):
        st["distance"].append(2000 + sek / 120 * 400)
        st["time"].append(st["time"][-1] + 1)
        st["heartrate"].append(150)
    s = compute_splits(st)
    assert len(s) == 3
    assert s[-1]["teil"] is True
    assert abs(s[-1]["km"] - 0.4) < 0.01
    assert s[-1]["pace_s_km"] == 300      # 120 s auf 0,4 km


def test_herzfrequenz_je_kilometer():
    st = lauf([300, 300])
    for i in range(301, len(st["heartrate"])):
        st["heartrate"][i] = 170
    s = compute_splits(st)
    assert s[0]["hf"] < s[1]["hf"]


def test_leere_und_kurze_streams():
    assert compute_splits({}) == []
    assert compute_splits({"distance": [0], "time": [0]}) == []
    # Kürzer als 50 m Rest: kein Teilsplit
    assert len(compute_splits(lauf([300]))) == 1


if __name__ == "__main__":
    f = 0
    for n, fn in sorted(globals().items()):
        if not n.startswith("test_") or not callable(fn): continue
        try: fn(); print(f"  ok     {n}")
        except AssertionError as e: f += 1; print(f"  FEHLER {n}: {e}")
        except Exception as e: f += 1; print(f"  CRASH  {n}: {type(e).__name__}: {e}")
    print(f"\n{'ALLE TESTS BESTANDEN' if not f else f'{f} fehlgeschlagen'}")
    sys.exit(1 if f else 0)
