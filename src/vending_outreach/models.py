"""Core records that flow through the pipeline."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

_WS = re.compile(r"\s+")
_NOISE = re.compile(r"\b(the|apartments?|apts?|residences?|at|of|llc|inc|lp)\b")


def property_key(name: str, address: str) -> str:
    """Stable identity for a property across re-runs and across sources.

    Google Places IDs churn and the same community shows up under slightly
    different names ("The Lofts at X" vs "Lofts at X Apartments"), so we key on
    a normalized name + street number instead.
    """
    n = _NOISE.sub(" ", (name or "").lower())
    n = _WS.sub(" ", re.sub(r"[^a-z0-9 ]", " ", n)).strip()
    street_no = ""
    m = re.match(r"\s*(\d+)", address or "")
    if m:
        street_no = m.group(1)
    return hashlib.sha1(f"{n}|{street_no}".encode()).hexdigest()[:16]


@dataclass
class Property:
    """An apartment community or a property-management group."""
    key: str
    name: str
    address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    phone: str = ""
    website: str = ""
    google_place_id: str = ""
    rating: Optional[float] = None
    rating_count: int = 0
    source: str = "places"

    # Filled by enrichment.
    unit_count: Optional[int] = None
    management_company: str = ""
    portfolio_size: int = 1
    event_signal: bool = False
    hosts_food_trucks: bool = False

    # Filled by scoring.
    score: int = 0
    score_reasons: str = ""

    # Set once synced.
    hubspot_company_id: str = ""

    def as_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Contact:
    """A named human at a property. Role matters more than seniority here --
    the community/lifestyle manager is the one who books food trucks."""
    property_key: str
    email: str
    first_name: str = ""
    last_name: str = ""
    title: str = ""
    source: str = ""
    confidence: float = 0.5
    hubspot_contact_id: str = ""

    @property
    def domain(self) -> str:
        return self.email.rsplit("@", 1)[-1].lower() if "@" in self.email else ""

    def display_name(self) -> str:
        return (self.first_name or "").strip() or "there"


@dataclass
class OutreachState:
    """Where a contact sits in the sequence."""
    email: str
    property_key: str
    step_index: int = 0
    last_sent_at: str = ""      # ISO8601 UTC
    next_due_at: str = ""       # ISO8601 UTC
    status: str = "pending"     # pending | in_sequence | replied | booked | stopped | exhausted
    offered_dates: str = ""     # JSON list of ISO dates named in the last email
    thread_id: str = ""
    notes: str = ""
    history: list[dict] = field(default_factory=list)
