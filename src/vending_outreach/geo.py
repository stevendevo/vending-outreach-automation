"""Distance helpers. Straight-line miles with a road-factor fudge is accurate
enough to decide whether a property is worth driving to; we don't need a
routing API for that call."""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Optional

EARTH_RADIUS_MI = 3958.8
# Typical ratio of road miles to great-circle miles in the Philly/NJ corridor.
ROAD_FACTOR = 1.25


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_MI * asin(sqrt(a))


def drive_miles(lat1: float, lng1: float,
                lat2: Optional[float], lng2: Optional[float]) -> Optional[float]:
    if lat2 is None or lng2 is None:
        return None
    return round(haversine_miles(lat1, lng1, lat2, lng2) * ROAD_FACTOR, 1)
