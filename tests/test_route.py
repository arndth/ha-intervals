"""Tests für die GPS-Route. Direkt: python3 tests/test_route.py"""
import sys
import types
from pathlib import Path

_COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "ha_intervals"
_pkg = types.ModuleType("ha_intervals")
_pkg.__path__ = [str(_COMPONENT)]
sys.modules.setdefault("ha_intervals", _pkg)
from ha_intervals.route import compact_route  # noqa: E402


def test_limits_and_endpoints():
    lat = [52 + i / 100000 for i in range(2682)]
    lon = [8 + i / 100000 for i in range(2682)]
    result = compact_route(lat, lon)
    assert len(result) == 240
    assert result[0] == [52, 8]
    assert result[-1] == [lat[-1], lon[-1]]


def test_invalid_coordinates():
    lat = [52, None, float('nan'), 91, 0, 52.1]
    lon = [8, 8, 8, 8, 0, 8.1]
    assert compact_route(lat, lon) == [[52, 8], [52.1, 8.1]]
    assert compact_route([52], [8]) == []
    assert compact_route([52, 53], [8]) == []
    assert compact_route([], []) == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print('  ok    ', name)
    print('ALLE TESTS BESTANDEN')
