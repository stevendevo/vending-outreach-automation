from datetime import date

import pytest

from vending_outreach.config import Config
from vending_outreach.slots import busy_days, format_dates, open_dates


@pytest.fixture
def cal():
    return Config.load().calendar


def _event(start, end, **kw):
    e = {"start": {"dateTime": start}, "end": {"dateTime": end}, "status": "confirmed"}
    e.update(kw)
    return e


def test_evening_event_blocks_that_day(cal):
    events = [_event("2026-09-22T16:30:00-04:00", "2026-09-22T18:30:00-04:00")]
    assert date(2026, 9, 22) in busy_days(events, cal)


def test_morning_event_does_not_block_the_dinner_slot(cal):
    events = [_event("2026-09-22T08:00:00-04:00", "2026-09-22T10:00:00-04:00")]
    assert date(2026, 9, 22) not in busy_days(events, cal)


def test_event_marked_free_does_not_block(cal):
    """A tentative hold on the calendar shouldn't cost us a bookable date."""
    events = [_event("2026-09-22T16:00:00-04:00", "2026-09-22T19:00:00-04:00",
                     transparency="transparent")]
    assert busy_days(events, cal) == set()


def test_cancelled_event_does_not_block(cal):
    events = [_event("2026-09-22T16:00:00-04:00", "2026-09-22T19:00:00-04:00",
                     status="cancelled")]
    assert busy_days(events, cal) == set()


def test_all_day_event_blocks_the_day(cal):
    events = [{"start": {"date": "2026-10-15"}, "end": {"date": "2026-10-26"},
               "status": "confirmed"}]
    blocked = busy_days(events, cal)
    assert date(2026, 10, 20) in blocked


def test_offered_dates_respect_lead_time_and_weekday(cal):
    today = date(2026, 8, 29)
    days = open_dates([], cal, today=today)
    assert len(days) == cal["slots_to_offer"]
    for d in days:
        assert d.weekday() in cal["preferred_weekdays"]
        assert (d - today).days >= cal["lead_time_days"]


def test_busy_dates_are_skipped_not_offered(cal):
    today = date(2026, 8, 29)
    first = open_dates([], cal, today=today)[0]
    blocking = [_event(f"{first.isoformat()}T16:00:00-04:00",
                       f"{first.isoformat()}T19:00:00-04:00")]
    assert first not in open_dates(blocking, cal, today=today)


def test_dates_format_the_way_a_person_reads_them(cal):
    assert format_dates([date(2026, 9, 22)], {}) == ["Tuesday, September 22"]
