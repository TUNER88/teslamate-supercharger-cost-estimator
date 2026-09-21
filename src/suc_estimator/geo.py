"""Geospatial matching helpers."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    r = 6_371_000.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlmb = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    return 2 * r * asin(sqrt(a))


def nearest(
    lat: float,
    lon: float,
    items: Iterable[T],
    get_latlon: Callable[[T], tuple[float, float]],
    max_m: float,
) -> tuple[T, float] | None:
    best: tuple[T, float] | None = None
    for item in items:
        ilat, ilon = get_latlon(item)
        d = haversine_m(lat, lon, ilat, ilon)
        if d > max_m:
            continue
        if best is None or d < best[1]:
            best = (item, d)
    return best
