"""Regression test against a real snapshot of the grill-e-vents calendar.

These are actual bookings from the Grilly Cheese calendar (Sept-Oct 2026). The
point is to confirm the gap finder never offers a date the truck is already
committed to, and still finds usable dates in a genuinely busy month.
"""
from datetime import date

import pytest

from vending_outreach.config import Config
from vending_outreach.slots import busy_days, open_dates

TZ = "-04:00"


def _ev(start, end, **kw):
    e = {"start": {"dateTime": f"{start}{TZ}"}, "end": {"dateTime": f"{end}{TZ}"},
         "status": "confirmed"}
    e.update(kw)
    return e


REAL_EVENTS = [
    _ev("2026-09-05T00:30:00", "2026-09-05T03:00:00"),   # Lina Ariyan (tentative)
    _ev("2026-09-05T20:00:00", "2026-09-05T23:00:00"),   # Pine Forge Academy
    _ev("2026-09-06T00:30:00", "2026-09-06T03:00:00"),   # Lina Ariyan
    _ev("2026-09-09T16:00:00", "2026-09-09T19:00:00"),   # The Jewish Center
    _ev("2026-09-12T18:00:00", "2026-09-12T20:00:00"),   # Napiorkowski
    _ev("2026-09-19T14:00:00", "2026-09-19T17:30:00"),   # Ridings of Woolwich
    _ev("2026-09-24T16:00:00", "2026-09-24T19:00:00"),   # BFT South River
    _ev("2026-09-26T16:30:00", "2026-09-26T21:30:00"),   # Lafayette Movie Night
    _ev("2026-09-27T13:00:00", "2026-09-27T15:00:00"),   # Frontline Arts
    _ev("2026-09-29T11:00:00", "2026-09-29T14:00:00"),   # Philly Business Ctr lunch
    _ev("2026-10-03T17:30:00", "2026-10-03T20:30:00"),   # Middletown birthday
    _ev("2026-10-03T22:30:00", "2026-10-04T01:00:00"),   # Susan McDermott
    _ev("2026-10-06T11:30:00", "2026-10-06T13:30:00"),   # Baldwin Richardson A
    _ev("2026-10-06T20:00:00", "2026-10-06T22:00:00"),   # Baldwin Richardson B
    _ev("2026-10-07T11:30:00", "2026-10-07T13:30:00"),   # Baldwin Richardson C
    _ev("2026-10-07T20:00:00", "2026-10-07T22:00:00"),   # Baldwin Richardson D
    _ev("2026-10-08T16:30:00", "2026-10-08T18:30:00"),   # BFT Aberdeen MD
    _ev("2026-10-23T12:00:00", "2026-10-23T14:00:00"),   # Bryn Mawr festival
    _ev("2026-10-24T23:30:00", "2026-10-25T02:00:00"),   # Siegel wedding
    # All-day travel block for the NC State Fair -- the truck is out of market.
    {"start": {"date": "2026-10-15"}, "end": {"date": "2026-10-26"},
     "status": "confirmed"},
]


@pytest.fixture
def cal():
    return Config.load().calendar


def test_committed_evenings_are_marked_busy(cal):
    blocked = busy_days(REAL_EVENTS, cal)
    # The Aberdeen MD church booking is a 4:30-6:30 PM Thursday.
    assert date(2026, 10, 8) in blocked
    # Baldwin Richardson runs a midday and an evening shift on the 6th and 7th.
    assert date(2026, 10, 6) in blocked
    assert date(2026, 10, 7) in blocked


def test_out_of_market_travel_week_is_blocked(cal):
    """The NC State Fair takes the truck out of the region for 11 days --
    offering an apartment date inside that window would be a broken promise."""
    blocked = busy_days(REAL_EVENTS, cal)
    for day in (date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)):
        assert day in blocked


def test_late_night_wedding_alone_does_not_block_that_afternoon(cal):
    """A 11:30 PM wedding after-party leaves the 5-7 PM resident slot free.
    (On the real calendar the 24th is busy anyway -- it falls inside the NC
    State Fair trip -- so the wedding is tested on its own here.)"""
    wedding = [_ev("2026-10-24T23:30:00", "2026-10-25T02:00:00")]
    assert date(2026, 10, 24) not in busy_days(wedding, cal)


def test_all_day_end_date_is_treated_as_exclusive(cal):
    """Google all-day events end the day *after* the last real day. The fair
    runs 10/15-10/25, so the 26th must come back bookable."""
    blocked = busy_days(REAL_EVENTS, cal)
    assert date(2026, 10, 25) in blocked
    assert date(2026, 10, 26) not in blocked


def test_offered_dates_never_collide_with_a_real_booking(cal):
    blocked = busy_days(REAL_EVENTS, cal)
    for day in open_dates(REAL_EVENTS, cal, today=date(2026, 8, 29), count=12):
        assert day not in blocked


def test_finds_usable_midweek_dates_in_a_busy_autumn(cal):
    days = open_dates(REAL_EVENTS, cal, today=date(2026, 8, 29), count=6)
    assert len(days) == 6
    assert all(d.weekday() in cal["preferred_weekdays"] for d in days)
    # Nothing inside the 21-day lead time.
    assert min(days) >= date(2026, 9, 19)
