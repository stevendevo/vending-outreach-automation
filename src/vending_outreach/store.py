"""SQLite persistence.

Every stage of the pipeline is resumable and idempotent: discovery can run
nightly and only ever adds new properties, enrichment skips what it has already
seen, and the sequencer will not double-send because sends are recorded here
before anything leaves the mailbox.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Optional

from .config import REPO_ROOT
from .models import Contact, OutreachState, Property

DEFAULT_DB = REPO_ROOT / "data" / "outreach.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS properties (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT, city TEXT, state TEXT, postal_code TEXT,
    lat REAL, lng REAL,
    phone TEXT, website TEXT,
    google_place_id TEXT, rating REAL, rating_count INTEGER,
    source TEXT,
    unit_count INTEGER,
    management_company TEXT,
    portfolio_size INTEGER DEFAULT 1,
    event_signal INTEGER DEFAULT 0,
    hosts_food_trucks INTEGER DEFAULT 0,
    score INTEGER DEFAULT 0,
    score_reasons TEXT,
    hubspot_company_id TEXT,
    enriched_at TEXT,
    discovered_at TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
    email TEXT PRIMARY KEY,
    property_key TEXT NOT NULL,
    first_name TEXT, last_name TEXT, title TEXT,
    source TEXT, confidence REAL DEFAULT 0.5,
    hubspot_contact_id TEXT,
    created_at TEXT,
    FOREIGN KEY (property_key) REFERENCES properties(key)
);
CREATE INDEX IF NOT EXISTS idx_contacts_property ON contacts(property_key);

CREATE TABLE IF NOT EXISTS outreach (
    email TEXT PRIMARY KEY,
    property_key TEXT NOT NULL,
    step_index INTEGER DEFAULT 0,
    last_sent_at TEXT,
    next_due_at TEXT,
    status TEXT DEFAULT 'pending',
    offered_dates TEXT,
    thread_id TEXT,
    notes TEXT,
    FOREIGN KEY (email) REFERENCES contacts(email)
);
CREATE INDEX IF NOT EXISTS idx_outreach_due ON outreach(status, next_due_at);

-- Append-only audit trail. Answers "what did we actually send this person".
CREATE TABLE IF NOT EXISTS sends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    property_key TEXT,
    step_key TEXT,
    subject TEXT,
    body TEXT,
    offered_dates TEXT,
    gmail_message_id TEXT,
    gmail_thread_id TEXT,
    mode TEXT,               -- draft | sent | dry-run
    sent_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_sends_email ON sends(email);
CREATE INDEX IF NOT EXISTS idx_sends_at ON sends(sent_at);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path = DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # ---------------------------------------------------------------- properties
    def upsert_property(self, p: Property) -> bool:
        """Returns True if this was a new property."""
        cur = self.conn.execute("SELECT key FROM properties WHERE key = ?", (p.key,))
        is_new = cur.fetchone() is None
        self.conn.execute(
            """
            INSERT INTO properties (key, name, address, city, state, postal_code,
                lat, lng, phone, website, google_place_id, rating, rating_count,
                source, unit_count, management_company, portfolio_size,
                event_signal, hosts_food_trucks, score, score_reasons,
                hubspot_company_id, discovered_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(key) DO UPDATE SET
                -- Never clobber good data with blanks on a re-discovery pass.
                name = excluded.name,
                address = COALESCE(NULLIF(excluded.address,''), properties.address),
                city = COALESCE(NULLIF(excluded.city,''), properties.city),
                state = COALESCE(NULLIF(excluded.state,''), properties.state),
                postal_code = COALESCE(NULLIF(excluded.postal_code,''), properties.postal_code),
                lat = COALESCE(excluded.lat, properties.lat),
                lng = COALESCE(excluded.lng, properties.lng),
                phone = COALESCE(NULLIF(excluded.phone,''), properties.phone),
                website = COALESCE(NULLIF(excluded.website,''), properties.website),
                google_place_id = COALESCE(NULLIF(excluded.google_place_id,''), properties.google_place_id),
                rating = COALESCE(excluded.rating, properties.rating),
                rating_count = MAX(excluded.rating_count, properties.rating_count)
            """,
            (p.key, p.name, p.address, p.city, p.state, p.postal_code, p.lat, p.lng,
             p.phone, p.website, p.google_place_id, p.rating, p.rating_count, p.source,
             p.unit_count, p.management_company, p.portfolio_size,
             int(p.event_signal), int(p.hosts_food_trucks), p.score, p.score_reasons,
             p.hubspot_company_id, utcnow()),
        )
        return is_new

    def update_property(self, key: str, **fields) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        vals = [int(v) if isinstance(v, bool) else v for v in fields.values()]
        self.conn.execute(f"UPDATE properties SET {cols} WHERE key = ?", (*vals, key))

    def get_property(self, key: str) -> Optional[Property]:
        row = self.conn.execute("SELECT * FROM properties WHERE key = ?", (key,)).fetchone()
        return _row_to_property(row) if row else None

    def properties(self, where: str = "", params: Iterable = ()) -> list[Property]:
        sql = "SELECT * FROM properties"
        if where:
            sql += f" WHERE {where}"
        return [_row_to_property(r) for r in self.conn.execute(sql, tuple(params))]

    def properties_needing_enrichment(self, limit: int = 500) -> list[Property]:
        return self.properties("enriched_at IS NULL LIMIT ?", (limit,))

    # ------------------------------------------------------------------ contacts
    def upsert_contact(self, c: Contact) -> None:
        self.conn.execute(
            """
            INSERT INTO contacts (email, property_key, first_name, last_name, title,
                                  source, confidence, hubspot_contact_id, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(email) DO UPDATE SET
                first_name = COALESCE(NULLIF(excluded.first_name,''), contacts.first_name),
                last_name  = COALESCE(NULLIF(excluded.last_name,''),  contacts.last_name),
                title      = COALESCE(NULLIF(excluded.title,''),      contacts.title),
                confidence = MAX(excluded.confidence, contacts.confidence)
            """,
            (c.email.lower(), c.property_key, c.first_name, c.last_name, c.title,
             c.source, c.confidence, c.hubspot_contact_id, utcnow()),
        )

    def contacts_for(self, property_key: str) -> list[Contact]:
        rows = self.conn.execute(
            "SELECT * FROM contacts WHERE property_key = ? ORDER BY confidence DESC",
            (property_key,),
        )
        return [_row_to_contact(r) for r in rows]

    def update_contact(self, email: str, **fields) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(
            f"UPDATE contacts SET {cols} WHERE email = ?", (*fields.values(), email.lower())
        )

    # ------------------------------------------------------------------ outreach
    def get_outreach(self, email: str) -> Optional[OutreachState]:
        row = self.conn.execute(
            "SELECT * FROM outreach WHERE email = ?", (email.lower(),)
        ).fetchone()
        if not row:
            return None
        return OutreachState(
            email=row["email"], property_key=row["property_key"],
            step_index=row["step_index"] or 0, last_sent_at=row["last_sent_at"] or "",
            next_due_at=row["next_due_at"] or "", status=row["status"] or "pending",
            offered_dates=row["offered_dates"] or "", thread_id=row["thread_id"] or "",
            notes=row["notes"] or "",
        )

    def upsert_outreach(self, s: OutreachState) -> None:
        self.conn.execute(
            """
            INSERT INTO outreach (email, property_key, step_index, last_sent_at,
                                  next_due_at, status, offered_dates, thread_id, notes)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(email) DO UPDATE SET
                step_index = excluded.step_index,
                last_sent_at = excluded.last_sent_at,
                next_due_at = excluded.next_due_at,
                status = excluded.status,
                offered_dates = excluded.offered_dates,
                thread_id = COALESCE(NULLIF(excluded.thread_id,''), outreach.thread_id),
                notes = excluded.notes
            """,
            (s.email.lower(), s.property_key, s.step_index, s.last_sent_at,
             s.next_due_at, s.status, s.offered_dates, s.thread_id, s.notes),
        )

    def set_outreach_status(self, email: str, status: str, note: str = "") -> None:
        self.conn.execute(
            "UPDATE outreach SET status = ?, notes = ? WHERE email = ?",
            (status, note, email.lower()),
        )

    def due_outreach(self, now_iso: str, limit: int = 200) -> list[sqlite3.Row]:
        """Contacts whose next sequence step is ready to go out."""
        return list(self.conn.execute(
            """
            SELECT o.*, c.first_name, c.last_name, c.title, p.name AS property_name,
                   p.city, p.state, p.unit_count, p.management_company, p.score
            FROM outreach o
            JOIN contacts c ON c.email = o.email
            JOIN properties p ON p.key = o.property_key
            WHERE o.status IN ('pending','in_sequence')
              AND (o.next_due_at IS NULL OR o.next_due_at = '' OR o.next_due_at <= ?)
            ORDER BY p.score DESC, o.next_due_at ASC
            LIMIT ?
            """,
            (now_iso, limit),
        ))

    # --------------------------------------------------------------------- sends
    def record_send(self, *, email: str, property_key: str, step_key: str,
                    subject: str, body: str, offered_dates: list[str],
                    message_id: str = "", thread_id: str = "", mode: str = "dry-run") -> None:
        self.conn.execute(
            """INSERT INTO sends (email, property_key, step_key, subject, body,
                                  offered_dates, gmail_message_id, gmail_thread_id,
                                  mode, sent_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (email.lower(), property_key, step_key, subject, body,
             json.dumps(offered_dates), message_id, thread_id, mode, utcnow()),
        )

    def sends_today(self, day_iso: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) c FROM sends WHERE mode IN ('sent','draft') AND sent_at LIKE ?",
            (f"{day_iso}%",),
        ).fetchone()
        return row["c"]

    def sends_today_for_domain(self, day_iso: str, domain: str) -> int:
        row = self.conn.execute(
            """SELECT COUNT(*) c FROM sends
               WHERE mode IN ('sent','draft') AND sent_at LIKE ? AND email LIKE ?""",
            (f"{day_iso}%", f"%@{domain}"),
        ).fetchone()
        return row["c"]

    def counts(self) -> dict[str, int]:
        q = lambda sql: self.conn.execute(sql).fetchone()[0]
        return {
            "properties": q("SELECT COUNT(*) FROM properties"),
            "enriched": q("SELECT COUNT(*) FROM properties WHERE enriched_at IS NOT NULL"),
            "scored": q("SELECT COUNT(*) FROM properties WHERE score > 0"),
            "contacts": q("SELECT COUNT(*) FROM contacts"),
            "in_sequence": q("SELECT COUNT(*) FROM outreach WHERE status='in_sequence'"),
            "replied": q("SELECT COUNT(*) FROM outreach WHERE status='replied'"),
            "booked": q("SELECT COUNT(*) FROM outreach WHERE status='booked'"),
            "emails_out": q("SELECT COUNT(*) FROM sends WHERE mode IN ('sent','draft')"),
        }


def _row_to_property(row: sqlite3.Row) -> Property:
    return Property(
        key=row["key"], name=row["name"], address=row["address"] or "",
        city=row["city"] or "", state=row["state"] or "",
        postal_code=row["postal_code"] or "", lat=row["lat"], lng=row["lng"],
        phone=row["phone"] or "", website=row["website"] or "",
        google_place_id=row["google_place_id"] or "", rating=row["rating"],
        rating_count=row["rating_count"] or 0, source=row["source"] or "",
        unit_count=row["unit_count"], management_company=row["management_company"] or "",
        portfolio_size=row["portfolio_size"] or 1,
        event_signal=bool(row["event_signal"]), hosts_food_trucks=bool(row["hosts_food_trucks"]),
        score=row["score"] or 0, score_reasons=row["score_reasons"] or "",
        hubspot_company_id=row["hubspot_company_id"] or "",
    )


def _row_to_contact(row: sqlite3.Row) -> Contact:
    return Contact(
        property_key=row["property_key"], email=row["email"],
        first_name=row["first_name"] or "", last_name=row["last_name"] or "",
        title=row["title"] or "", source=row["source"] or "",
        confidence=row["confidence"] or 0.5,
        hubspot_contact_id=row["hubspot_contact_id"] or "",
    )
