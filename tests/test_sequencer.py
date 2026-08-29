"""Guardrail tests. A bug in this module means double-emailing a prospect or
mailing someone who already replied, so each rail gets an explicit test."""
from datetime import datetime, timedelta, timezone

import pytest

from vending_outreach.config import Config
from vending_outreach.models import Contact, OutreachState, Property
from vending_outreach.outreach.sequencer import (
    Sequencer, SendBlocked, enqueue_candidates, within_send_window)
from vending_outreach.store import Store, utcnow


class FakeGoogle:
    """Stands in for Gmail/Calendar so tests never touch the network."""

    def __init__(self, replies=None, events=None, fail_reply_check=False):
        self.replies = set(replies or [])
        self.events = events or []
        self.fail_reply_check = fail_reply_check
        self.sent = []
        self.drafts = []

    def has_reply_from(self, email, after_iso=""):
        if self.fail_reply_check:
            raise RuntimeError("gmail unavailable")
        return email in self.replies

    def send(self, to, subject, body, thread_id=""):
        self.sent.append((to, subject))
        return {"message_id": f"m{len(self.sent)}", "thread_id": "t1"}

    def create_draft(self, to, subject, body, thread_id=""):
        self.drafts.append((to, subject))
        return {"message_id": f"d{len(self.drafts)}", "thread_id": "t1", "draft_id": "x"}

    def list_events(self, *a, **kw):
        return self.events


@pytest.fixture
def cfg():
    return Config.load()


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.sqlite3")
    yield s
    s.close()


def seed(store, email="leasing@bigcommunity.com", score=80, units=400):
    prop = Property(key="p1", name="Big Community", city="Cherry Hill", state="NJ",
                    lat=39.93, lng=-75.03, unit_count=units, score=score)
    store.upsert_property(prop)
    store.update_property("p1", score=score)
    store.upsert_contact(Contact(property_key="p1", email=email,
                                 first_name="Dana", title="Community Manager"))
    store.upsert_outreach(OutreachState(email=email, property_key="p1"))
    store.conn.commit()
    return prop


# ------------------------------------------------------------------ dry run
def test_dry_run_sends_nothing(cfg, store):
    seed(store)
    google = FakeGoogle()
    results = Sequencer(cfg, store, google=google).run(mode="dry-run")
    assert results[0]["action"] == "dry-run"
    assert google.sent == [] and google.drafts == []


def test_dry_run_does_not_advance_the_sequence(cfg, store):
    """A dry run must be repeatable without burning sequence steps."""
    seed(store)
    seq = Sequencer(cfg, store, google=FakeGoogle())
    seq.run(mode="dry-run")
    seq.run(mode="dry-run")
    assert store.get_outreach("leasing@bigcommunity.com").step_index == 0


# ----------------------------------------------------------------- no repeats
def test_live_send_advances_and_does_not_resend_immediately(cfg, store):
    seed(store)
    google = FakeGoogle()
    seq = Sequencer(cfg, store, google=google)
    seq.run(mode="live", ignore_window=True)
    assert len(google.sent) == 1
    state = store.get_outreach("leasing@bigcommunity.com")
    assert state.step_index == 1 and state.status == "in_sequence"

    # Immediately re-running must not fire the next step early.
    seq.run(mode="live", ignore_window=True)
    assert len(google.sent) == 1


def test_next_step_fires_once_it_is_due(cfg, store):
    email = "leasing@bigcommunity.com"
    seed(store)
    google = FakeGoogle()
    seq = Sequencer(cfg, store, google=google)
    seq.run(mode="live", ignore_window=True)

    # Wind the clock forward past the configured delay.
    store.conn.execute("UPDATE outreach SET next_due_at = ? WHERE email = ?",
                       ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), email))
    store.conn.commit()
    seq.run(mode="live", ignore_window=True)
    assert len(google.sent) == 2
    assert google.sent[0][1] != google.sent[1][1]  # different step, different subject


# -------------------------------------------------------------------- replies
def test_reply_stops_the_sequence(cfg, store):
    email = "leasing@bigcommunity.com"
    seed(store)
    google = FakeGoogle(replies={email})
    seq = Sequencer(cfg, store, google=google)
    seq.run(mode="live", ignore_window=True)          # step 1 goes out
    store.conn.execute("UPDATE outreach SET next_due_at = ? WHERE email = ?",
                       ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), email))
    store.conn.commit()
    seq.run(mode="live", ignore_window=True)          # they replied in between
    assert len(google.sent) == 1
    assert store.get_outreach(email).status == "replied"


def test_unverifiable_reply_status_defers_rather_than_sends(cfg, store):
    """If Gmail is down we must not guess -- a missed follow-up beats emailing
    someone who already answered."""
    email = "leasing@bigcommunity.com"
    seed(store)
    store.upsert_outreach(OutreachState(email=email, property_key="p1",
                                        step_index=1, last_sent_at=utcnow(),
                                        status="in_sequence"))
    store.conn.commit()
    google = FakeGoogle(fail_reply_check=True)
    results = Sequencer(cfg, store, google=google).run(mode="live", ignore_window=True)
    assert results[0]["action"] == "deferred"
    assert google.sent == []


# ---------------------------------------------------------------- suppression
def test_suppressed_domain_is_never_contacted(cfg, store, monkeypatch):
    seed(store, email="hello@bestfoodtrucks.com")
    google = FakeGoogle()
    seq = Sequencer(cfg, store, google=google)
    results = seq.run(mode="live", ignore_window=True)
    assert results[0]["action"] == "blocked"
    assert google.sent == []


def test_suppressed_contacts_are_not_queued(cfg, store):
    prop = Property(key="p9", name="Vendor Co", score=90)
    store.upsert_property(prop)
    store.update_property("p9", score=90)
    store.upsert_contact(Contact(property_key="p9", email="a@bestfoodtrucks.com"))
    store.conn.commit()
    assert enqueue_candidates(cfg, store) == 0


# ---------------------------------------------------------------------- caps
def test_daily_cap_defers_further_sends(cfg, store):
    cfg.raw["outreach"]["daily_send_cap"] = 1
    seed(store, email="a@one.com")
    store.upsert_property(Property(key="p2", name="Second", score=70))
    store.update_property("p2", score=70)
    store.upsert_contact(Contact(property_key="p2", email="b@two.com"))
    store.upsert_outreach(OutreachState(email="b@two.com", property_key="p2"))
    store.conn.commit()

    google = FakeGoogle()
    results = Sequencer(cfg, store, google=google).run(mode="live", ignore_window=True)
    actions = [r["action"] for r in results]
    assert actions.count("live") == 1
    assert "deferred" in actions
    assert len(google.sent) == 1


def test_per_domain_cap_limits_one_management_company(cfg, store):
    """One property manager should not get five emails in a morning."""
    cfg.raw["outreach"]["per_domain_daily_cap"] = 1
    for i, email in enumerate(["a@morgan.com", "b@morgan.com"]):
        key = f"pm{i}"
        store.upsert_property(Property(key=key, name=f"Prop {i}", score=80))
        store.update_property(key, score=80)
        store.upsert_contact(Contact(property_key=key, email=email))
        store.upsert_outreach(OutreachState(email=email, property_key=key))
    store.conn.commit()

    google = FakeGoogle()
    results = Sequencer(cfg, store, google=google).run(mode="live", ignore_window=True)
    assert len(google.sent) == 1
    assert any(r["action"] == "deferred" for r in results)


# ------------------------------------------------------------- send windows
def test_weekend_is_outside_the_send_window(cfg):
    saturday = datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)
    ok, why = within_send_window(cfg, saturday)
    assert not ok and "send days" in why


def test_late_night_is_outside_the_send_window(cfg):
    from zoneinfo import ZoneInfo
    tuesday_11pm = datetime(2026, 9, 8, 23, 0, tzinfo=ZoneInfo("America/New_York"))
    ok, _ = within_send_window(cfg, tuesday_11pm)
    assert not ok


def test_tuesday_midmorning_is_inside_the_window(cfg):
    from zoneinfo import ZoneInfo
    tuesday_10am = datetime(2026, 9, 8, 10, 0, tzinfo=ZoneInfo("America/New_York"))
    ok, _ = within_send_window(cfg, tuesday_10am)
    assert ok


def test_live_run_refuses_outside_the_window_by_default(cfg, store, monkeypatch):
    seed(store)
    google = FakeGoogle()
    monkeypatch.setattr("vending_outreach.outreach.sequencer.within_send_window",
                        lambda c, n=None: (False, "outside window"))
    results = Sequencer(cfg, store, google=google).run(mode="live")
    assert results == []
    assert google.sent == []


# --------------------------------------------------------------------- audit
def test_every_send_is_recorded_before_it_goes_out(cfg, store):
    seed(store)
    Sequencer(cfg, store, google=FakeGoogle()).run(mode="live", ignore_window=True)
    row = store.conn.execute("SELECT * FROM sends").fetchone()
    assert row["mode"] == "sent"
    assert row["subject"] and row["body"]
    assert "Big Community" in row["subject"]
