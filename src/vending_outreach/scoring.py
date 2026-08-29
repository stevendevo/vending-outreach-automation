"""Fit scoring.

The point of a score here is triage: we can personalize maybe 40 emails a day,
and there are thousands of apartment communities in the market. Score decides
who gets those 40. Every component is explainable so a low score can be argued
with rather than trusted blindly.
"""
from __future__ import annotations

from typing import Optional

from .config import Config
from .geo import drive_miles
from .models import Property


def _unit_points(units: Optional[int], bands: list[dict]) -> tuple[float, bool]:
    if units is None:
        return 0.0, False
    for band in bands:         # bands are ordered high -> low in config
        if units >= band["min_units"]:
            return float(band["points"]), True
    return 0.0, True


def _proximity_points(miles: Optional[float], max_miles: float) -> tuple[float, bool]:
    if miles is None:
        return 0.0, False
    if miles <= 15:
        return 1.0, True
    if miles >= max_miles:
        return 0.0, True
    # Linear falloff from 15 miles out to the configured limit.
    return round(1.0 - (miles - 15) / (max_miles - 15), 3), True


def _portfolio_points(size: int) -> tuple[float, bool]:
    if size >= 10:
        return 1.0, True
    if size >= 5:
        return 0.75, True
    if size >= 2:
        return 0.5, True
    return 0.15, True


def _rating_points(count: int) -> tuple[float, bool]:
    if not count:
        return 0.0, False     # no reviews pulled yet != an unpopular community
    if count >= 300:
        return 1.0, True
    if count >= 120:
        return 0.7, True
    if count >= 40:
        return 0.45, True
    return 0.15, True


def _event_points(prop: Property, enriched: bool) -> tuple[float, bool]:
    if prop.hosts_food_trucks:
        return 1.0, True
    if prop.event_signal:
        return 0.6, True
    # Absent a site crawl we have no opinion; after one, silence is a real
    # (mild) negative signal.
    return (0.0, True) if enriched else (0.0, False)


def score_property(prop: Property, cfg: Config, has_contact: bool,
                   enriched: bool = True) -> tuple[int, str]:
    """Return (0-100 score, human-readable reasons).

    Only signals we actually have are counted, in the numerator *and* the
    denominator. A property we simply have not enriched yet is not the same
    thing as a bad fit, and scoring it as one would bury good targets.
    """
    sc = cfg.scoring
    w = sc["weights"]
    biz = cfg.business
    miles = drive_miles(biz["base_lat"], biz["base_lng"], prop.lat, prop.lng)

    parts: dict[str, tuple[float, bool]] = {
        "unit_count": _unit_points(prop.unit_count, sc["unit_count_bands"]),
        "proximity": _proximity_points(miles, float(cfg.discovery["max_distance_miles"])),
        "portfolio_size": _portfolio_points(prop.portfolio_size),
        "event_signal": _event_points(prop, enriched),
        "rating_volume": _rating_points(prop.rating_count),
        "contactability": (1.0 if has_contact else 0.0, True),
    }

    known_weight = sum(w[k] for k, (_, known) in parts.items() if known)
    raw = sum(pts * w[k] for k, (pts, known) in parts.items() if known)
    score = int(round(100 * raw / known_weight)) if known_weight else 0

    reasons = []
    if prop.unit_count:
        reasons.append(f"{prop.unit_count} units")
    else:
        reasons.append("unit count unknown")
    if miles is not None:
        reasons.append(f"{miles} mi from base")
    if prop.portfolio_size > 1:
        reasons.append(f"{prop.portfolio_size}-property portfolio ({prop.management_company})")
    if prop.hosts_food_trucks:
        reasons.append("site mentions food trucks")
    elif prop.event_signal:
        reasons.append("runs resident events")
    if prop.rating_count:
        reasons.append(f"{prop.rating_count} Google reviews")
    if not has_contact:
        reasons.append("no email found yet")
    if not enriched:
        reasons.append("not enriched yet")

    return score, "; ".join(reasons)


def run_scoring(cfg: Config, store) -> dict[str, int]:
    hard_min = cfg.scoring["hard_min_units"]
    threshold = cfg.scoring["min_score_to_contact"]
    stats = {"scored": 0, "above_threshold": 0, "too_small": 0}

    for prop in store.properties():
        # A 24-unit building cannot clear a $1,050 guarantee. Skip, don't score.
        if prop.unit_count is not None and prop.unit_count < hard_min:
            store.update_property(prop.key, score=0,
                                  score_reasons=f"below {hard_min}-unit minimum")
            stats["too_small"] += 1
            continue
        has_contact = bool(store.contacts_for(prop.key))
        enriched = store.conn.execute(
            "SELECT enriched_at FROM properties WHERE key = ?", (prop.key,)
        ).fetchone()[0] is not None
        score, reasons = score_property(prop, cfg, has_contact, enriched)
        store.update_property(prop.key, score=score, score_reasons=reasons)
        stats["scored"] += 1
        if score >= threshold:
            stats["above_threshold"] += 1
    store.conn.commit()
    return stats
