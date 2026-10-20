"""GPS-Route für die Darstellung: validieren und begrenzt ausgeben."""
from __future__ import annotations

import math


def compact_route(latitudes: list, longitudes: list, max_points: int = 240) -> list[list[float]]:
    """Keine Rohstreams im Panel. Start/Ende bleiben erhalten.

    Ungültige Koordinaten werden entfernt. Ein Downsample über Indexpositionen
    hält die Rückgabe auch bei sehr langen Aktivitäten unter Kontrolle.
    """
    if not isinstance(latitudes, list) or not isinstance(longitudes, list):
        return []
    points = []
    for lat, lon in zip(latitudes, longitudes):
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        if not (math.isfinite(lat) and math.isfinite(lon)):
            continue
        if not (-85 <= lat <= 85 and -180 <= lon <= 180):
            continue
        if lat == 0 and lon == 0:
            continue
        points.append([round(float(lat), 6), round(float(lon), 6)])
    if len(points) < 2:
        return []
    count = min(len(points), max(2, max_points))
    return [points[i * (len(points) - 1) // (count - 1)] for i in range(count)]
