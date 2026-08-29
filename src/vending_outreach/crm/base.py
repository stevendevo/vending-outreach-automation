"""CRM sink interface.

The pipeline does not care where records land. `sync` resolves a primary sink
from config and optionally mirrors contacts into a secondary one, so moving off
HubSpot (or back) is a config change, not a rewrite.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Protocol

from ..models import Contact, Property


@dataclass
class LeadPayload:
    """One apartment community and the person we're pitching, flattened.

    This is the neutral shape every adapter receives; each one maps it onto
    whatever its own API expects.
    """
    external_id: str                 # our stable property key
    name: str
    address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    phone: str = ""
    website: str = ""
    unit_count: Optional[int] = None
    management_company: str = ""
    portfolio_size: int = 1
    score: int = 0
    score_reasons: str = ""
    source: str = "vending-outreach-automation"
    lead_type: str = "apartment_vending"
    status: str = "new"

    contact_email: str = ""
    contact_first_name: str = ""
    contact_last_name: str = ""
    contact_title: str = ""

    offer_model: str = "resident-pay vending"
    offer_guarantee_usd: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in ("", None)}


@dataclass
class ActivityPayload:
    """An outreach email we sent, for the CRM's timeline."""
    external_id: str
    contact_email: str
    kind: str = "email"
    subject: str = ""
    body: str = ""
    step: str = ""
    occurred_at: str = ""
    offered_dates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in ("", None, [])}


class CRMAdapter(Protocol):
    name: str

    def upsert_lead(self, lead: LeadPayload) -> str: ...
    def log_activity(self, activity: ActivityPayload) -> str: ...


def lead_from(prop: Property, contact: Optional[Contact], cfg) -> LeadPayload:
    return LeadPayload(
        external_id=prop.key,
        name=prop.name,
        address=prop.address,
        city=prop.city,
        state=prop.state,
        postal_code=prop.postal_code,
        phone=prop.phone,
        website=prop.website,
        unit_count=prop.unit_count,
        management_company=prop.management_company,
        portfolio_size=prop.portfolio_size,
        score=prop.score,
        score_reasons=prop.score_reasons,
        contact_email=contact.email if contact else "",
        contact_first_name=contact.first_name if contact else "",
        contact_last_name=contact.last_name if contact else "",
        contact_title=contact.title if contact else "",
        offer_guarantee_usd=float(cfg.offer["sales_guarantee_usd"]),
        offer_model=cfg.offer["model"],
    )
