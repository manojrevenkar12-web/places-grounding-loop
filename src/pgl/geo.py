"""Small geodesy: distances and offsets on a sphere, and a metric grid for blocking."""

from __future__ import annotations

import math

R = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def offset(lat: float, lon: float, distance_m: float, bearing_deg: float) -> tuple[float, float]:
    b = math.radians(bearing_deg)
    dlat = distance_m * math.cos(b) / R
    dlon = distance_m * math.sin(b) / (R * math.cos(math.radians(lat)))
    return lat + math.degrees(dlat), lon + math.degrees(dlon)


def cell(lat: float, lon: float, size_m: float) -> tuple[int, int]:
    """A grid cell of roughly size_m metres, for blocking candidate pairs."""
    y = lat * 111_320.0 / size_m
    x = lon * 111_320.0 * math.cos(math.radians(52.5)) / size_m
    return int(math.floor(y)), int(math.floor(x))
