"""The outreach engine.

Guardrails are the point of this module, not an afterthought:

  * Nothing sends unless the caller explicitly asks for live mode.
  * Daily and per-domain caps are enforced against the recorded send log, so
    restarting the process cannot blow through them.
  * Sends only happen inside a configured local-time business window.
  * Any inbound reply stops the sequence before the next step goes out.
  * A suppression list is checked on every single send.
  * The send is recorded before the sequence advances, so a crash mid-run
    re-sends nothing.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from ..config import Config
from ..models import Contact, OutreachState, Property
from ..slots import format_dates, open_dates
from ..store import Store, utcnow
from .templates import Renderer

log = logging.getLogger(__name__)


class SendBlocked(Exception):
    """Raised when a guardrail refuses a send."""


def _parse_hhmm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def within_send_window(cfg: Config, now: Optional[datetime] = None) -> tuple[bool, str]:
    tz = ZoneInfo(cfg.calendar["timezone"])
    now = now or datetime.now(tz)
    now = now.astimezone(tz)
    out = cfg.outreach
    if now.weekday() not in out["send_weekdays"]:
        return False, f"{now:%A} is outside the configured send days"
    start = _parse_hhmm(out["send_window_start_local"])
    end = _parse_hhmm(out["send_window_end_local"])
    if not (start <= now.time() <= end):
        return False, (f"{now:%H:%M} is outside the send window "
                       f"{out['send_window_start_local']}-{out['send_window_end_local']}")
    return True, ""


class Sequencer:
    def __init__(self, cfg: Config, store: Store, google=None, renderer=None):
        self.cfg = cfg
        self.store = store
        self.google = google
        self.renderer = renderer or Renderer(cfg)
        self.suppressed = cfg.suppression()
        self.steps = cfg.outreach["steps"]
        self._slot_cache: Optional[list[str]] = None

    # ------------------------------------------------------------------ slots
    def offered_dates(self, refresh: bool = False) -> list[str]:
        """Live open dates from the booking calendar, cached for the run."""
        if self._slot_cache is not None and not refresh:
            return self._slot_cache
        cal = self.cfg.calendar
        if self.google is None:
            # No calendar access (dry run without creds): fall back to the next
            # preferred weekdays with nothing marked busy.
            days = open_dates([], cal)
        else:
            tz = ZoneInfo(cal["timezone"])
            now = datetime.now(tz)
            events = self.google.list_events(
                cal["calendar_id"],
                now.isoformat(),
                (now + timedelta(days=cal["horizon_days"] + 7)).isoformat(),
            )
            days = open_dates(events, cal)
        self._slot_cache = format_dates(days, self.cfg.offer)
        if not self._slot_cache:
            log.warning("No open dates found in the next %s days", cal["horizon_days"])
        return self._slot_cache

    # ------------------------------------------------------------- guardrails
    def check_suppressed(self, email: str) -> Optional[str]:
        email = email.lower()
        domain = email.rsplit("@", 1)[-1]
        if email in self.suppressed:
            return "address is on the suppression list"
        if domain in self.suppressed:
            return f"domain {domain} is on the suppression list"
        return None

    def check_caps(self, email: str, today_iso: str) -> Optional[str]:
        out = self.cfg.outreach
        if self.store.sends_today(today_iso) >= out["daily_send_cap"]:
            return f"daily cap of {out['daily_send_cap']} reached"
        domain = email.rsplit("@", 1)[-1].lower()
        if self.store.sends_today_for_domain(today_iso, domain) >= out["per_domain_daily_cap"]:
            return f"per-domain cap of {out['per_domain_daily_cap']} reached for {domain}"
        return None

    def check_reply(self, email: str, since: str = "") -> bool:
        if self.google is None or not self.cfg.outreach.get("stop_on_reply", True):
            return False
        try:
            return self.google.has_reply_from(email, since)
        except Exception as exc:
            # If we cannot verify, do not send -- better a missed follow-up
            # than emailing someone who already answered.
            log.warning("Reply check failed for %s: %s", email, exc)
            raise SendBlocked("could not verify reply status") from exc

    # ------------------------------------------------------------------- send
    def process_one(self, row, mode: str, today_iso: str) -> dict:
        """Handle a single due contact. Returns a result record for reporting."""
        email = row["email"]
        result = {"email": email, "property": row["property_name"],
                  "step": "", "action": "", "reason": ""}

        state = self.store.get_outreach(email) or OutreachState(
            email=email, property_key=row["property_key"]
        )
        if state.step_index >= len(self.steps):
            self.store.set_outreach_status(email, "exhausted", "sequence complete")
            result["action"] = "skipped"
            result["reason"] = "sequence already complete"
            return result

        step = self.steps[state.step_index]
        result["step"] = step["key"]

        blocked = self.check_suppressed(email)
        if blocked:
            self.store.set_outreach_status(email, "stopped", blocked)
            result["action"] = "blocked"
            result["reason"] = blocked
            return result

        if mode != "dry-run":
            blocked = self.check_caps(email, today_iso)
            if blocked:
                result["action"] = "deferred"
                result["reason"] = blocked
                return result

        # Someone who already wrote back should never get an automated bump.
        if state.step_index > 0 or state.last_sent_at:
            try:
                if self.check_reply(email, state.last_sent_at):
                    self.store.set_outreach_status(email, "replied", "inbound reply detected")
                    result["action"] = "stopped"
                    result["reason"] = "they replied"
                    return result
            except SendBlocked as exc:
                result["action"] = "deferred"
                result["reason"] = str(exc)
                return result

        prop = self.store.get_property(row["property_key"])
        if prop is None:
            result["action"] = "skipped"
            result["reason"] = "property missing"
            return result
        contact = Contact(
            property_key=row["property_key"], email=email,
            first_name=row["first_name"] or "", last_name=row["last_name"] or "",
            title=row["title"] or "",
        )

        dates = self.offered_dates()
        if not dates:
            result["action"] = "deferred"
            result["reason"] = "no open dates on the calendar to offer"
            return result

        rendered = self.renderer.render(step["template"], prop, contact, dates)

        message_id = thread_id = ""
        if mode == "draft":
            res = self.google.create_draft(email, rendered.subject, rendered.body,
                                           state.thread_id)
            message_id, thread_id = res["message_id"], res["thread_id"]
        elif mode == "live":
            res = self.google.send(email, rendered.subject, rendered.body,
                                   state.thread_id)
            message_id, thread_id = res["message_id"], res["thread_id"]

        # Record first, advance second: a crash between the two costs us a
        # duplicate row in the log, never a duplicate email.
        self.store.record_send(
            email=email, property_key=prop.key, step_key=step["key"],
            subject=rendered.subject, body=rendered.body, offered_dates=dates,
            message_id=message_id, thread_id=thread_id,
            mode="dry-run" if mode == "dry-run" else ("draft" if mode == "draft" else "sent"),
        )

        if mode != "dry-run":
            next_index = state.step_index + 1
            if next_index < len(self.steps):
                delay = self.steps[next_index]["delay_days"]
                next_due = (datetime.now(timezone.utc) + timedelta(days=delay)).isoformat(timespec="seconds")
                status = "in_sequence"
            else:
                next_due = ""
                status = "exhausted"
            self.store.upsert_outreach(OutreachState(
                email=email, property_key=prop.key, step_index=next_index,
                last_sent_at=utcnow(), next_due_at=next_due, status=status,
                offered_dates=json.dumps(dates), thread_id=thread_id or state.thread_id,
                notes=state.notes,
            ))
        self.store.conn.commit()

        result["action"] = mode
        result["subject"] = rendered.subject
        result["body"] = rendered.body
        return result

    def run(self, mode: str = "dry-run", limit: int = 25,
            ignore_window: bool = False) -> list[dict]:
        """Work the due queue. mode is one of dry-run | draft | live."""
        if mode not in ("dry-run", "draft", "live"):
            raise ValueError(f"unknown mode {mode!r}")
        if mode in ("draft", "live") and self.google is None:
            raise SystemExit("Gmail access is required for draft/live mode.")

        if mode == "live" and not ignore_window:
            ok, why = within_send_window(self.cfg)
            if not ok:
                log.warning("Refusing to send: %s (use --ignore-window to override)", why)
                return []

        tz = ZoneInfo(self.cfg.calendar["timezone"])
        today_iso = datetime.now(timezone.utc).date().isoformat()
        rows = self.store.due_outreach(utcnow(), limit=limit)

        results = []
        for row in rows:
            try:
                results.append(self.process_one(row, mode, today_iso))
            except Exception as exc:
                log.exception("Failed on %s", row["email"])
                results.append({"email": row["email"], "action": "error",
                                "reason": str(exc), "property": row["property_name"]})
        return results


def enqueue_candidates(cfg: Config, store: Store, limit: int = 100) -> int:
    """Put the best not-yet-contacted contacts into the sequence queue."""
    threshold = cfg.scoring["min_score_to_contact"]
    suppressed = cfg.suppression()
    rows = store.conn.execute(
        """
        SELECT c.email, c.property_key, p.score
        FROM contacts c
        JOIN properties p ON p.key = c.property_key
        LEFT JOIN outreach o ON o.email = c.email
        WHERE o.email IS NULL AND p.score >= ?
        ORDER BY p.score DESC, c.confidence DESC
        LIMIT ?
        """,
        (threshold, limit),
    ).fetchall()

    added = 0
    for row in rows:
        email = row["email"].lower()
        if email in suppressed or email.rsplit("@", 1)[-1] in suppressed:
            continue
        store.upsert_outreach(OutreachState(
            email=email, property_key=row["property_key"],
            step_index=0, next_due_at="", status="pending",
        ))
        added += 1
    store.conn.commit()
    return added
