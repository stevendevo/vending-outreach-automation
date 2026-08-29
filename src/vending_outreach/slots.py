"""Open-date finder.

Naming three real open dates is what turns a cold email into a booking, so the
sequencer pulls live availability off the grill-e-vents Google Calendar rather
than making vague "we have availability" claims.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)


def _parse_local(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def _event_bounds(event: dict, tz: ZoneInfo) -> Optional[tuple[datetime, datetime]]:
    start, end = event.get("start", {}), event.get("end", {})
    try:
        if "dateTime" in start:
            s = datetime.fromisoformat(start["dateTime"]).astimezone(tz)
            e = datetime.fromisoformat(end["dateTime"]).astimezone(tz)
        elif "date" in start:
            # All-day: treat the whole local day as blocked.
            d = date.fromisoformat(start["date"][:10])
            de = date.fromisoformat(end["date"][:10])
            s = datetime.combine(d, time.min, tzinfo=tz)
            e = datetime.combine(de, time.min, tzinfo=tz)
        else:
            return None
    except ValueError:
        return None
    return s, e


def busy_days(events: list[dict], cfg_cal: dict) -> set[date]:
    """Local dates where an existing event overlaps the vending service window."""
    tz = ZoneInfo(cfg_cal["timezone"])
    win_start = _parse_local(cfg_cal["block_start_local"])
    win_end = _parse_local(cfg_cal["block_end_local"])
    blocked: set[date] = set()

    for event in events:
        # An event explicitly marked free (a hold, a tentative note) doesn't
        # take the truck off the road.
        if event.get("transparency") == "transparent":
            continue
        if event.get("status") == "cancelled":
            continue
        bounds = _event_bounds(event, tz)
        if not bounds:
            continue
        start, end = bounds
        day = start.date()
        while day <= end.date():
            window_start = datetime.combine(day, win_start, tzinfo=tz)
            window_end = datetime.combine(day, win_end, tzinfo=tz)
            if start < window_end and end > window_start:
                blocked.add(day)
            day += timedelta(days=1)
    return blocked


def open_dates(events: list[dict], cfg_cal: dict, today: Optional[date] = None,
               count: Optional[int] = None) -> list[date]:
    """Next N open preferred-weekday dates beyond the lead time."""
    tz = ZoneInfo(cfg_cal["timezone"])
    today = today or datetime.now(tz).date()
    blocked = busy_days(events, cfg_cal)
    preferred = set(cfg_cal["preferred_weekdays"])
    want = count or cfg_cal["slots_to_offer"]

    out: list[date] = []
    start = today + timedelta(days=cfg_cal["lead_time_days"])
    for offset in range(cfg_cal["horizon_days"]):
        day = start + timedelta(days=offset)
        if day.weekday() not in preferred or day in blocked:
            continue
        out.append(day)
        if len(out) >= want:
            break
    return out


def format_dates(days: list[date], offer: dict) -> list[str]:
    """"Tuesday, September 22" -- how a human would read it back."""
    return [d.strftime("%A, %B %-d") for d in days]
