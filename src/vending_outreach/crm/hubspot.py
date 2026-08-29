"""HubSpot sync.

Mirrors the pipeline into portal 6451718 so the CRM stays the single source of
truth for what happened with each property. Uses the existing Event Quote
Pipeline and its Vending Request stages rather than inventing new ones.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import requests

from ..config import Config
from ..models import Contact, Property

log = logging.getLogger(__name__)
BASE = "https://api.hubapi.com"


class HubSpotClient:
    def __init__(self, token: str, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def _call(self, method: str, path: str, **kwargs) -> dict:
        resp = self.session.request(method, f"{BASE}{path}", timeout=30, **kwargs)
        if resp.status_code >= 400:
            log.error("HubSpot %s %s -> %s: %s", method, path,
                      resp.status_code, resp.text[:400])
            resp.raise_for_status()
        return resp.json() if resp.text else {}

    # ----------------------------------------------------------------- search
    def find_company(self, name: str, domain: str = "") -> Optional[str]:
        """Domain first (exact), then name. Avoids duplicating existing records."""
        for prop_name, value in (("domain", domain), ("name", name)):
            if not value:
                continue
            body = {
                "filterGroups": [{"filters": [
                    {"propertyName": prop_name, "operator": "EQ", "value": value}
                ]}],
                "properties": ["name", "domain"],
                "limit": 1,
            }
            results = self._call("POST", "/crm/v3/objects/companies/search",
                                 json=body).get("results", [])
            if results:
                return results[0]["id"]
        return None

    def find_contact(self, email: str) -> Optional[str]:
        body = {
            "filterGroups": [{"filters": [
                {"propertyName": "email", "operator": "EQ", "value": email.lower()}
            ]}],
            "properties": ["email"],
            "limit": 1,
        }
        results = self._call("POST", "/crm/v3/objects/contacts/search",
                             json=body).get("results", [])
        return results[0]["id"] if results else None

    # ----------------------------------------------------------------- upsert
    def upsert_company(self, prop: Property, owner_id: str) -> str:
        domain = ""
        if prop.website:
            domain = (prop.website.split("//")[-1].split("/")[0]
                      .replace("www.", "").lower())
        props: dict[str, Any] = {
            "name": prop.name,
            "domain": domain,
            "city": prop.city,
            "state": prop.state,
            "zip": prop.postal_code,
            "address": prop.address,
            "phone": prop.phone,
            "website": prop.website,
            "industry": "REAL_ESTATE",
            "hubspot_owner_id": owner_id,
            "description": (
                f"Resident vending target. Score {prop.score}/100. "
                f"{prop.score_reasons}"
            ),
        }
        props = {k: v for k, v in props.items() if v not in ("", None)}
        existing = self.find_company(prop.name, domain)
        if existing:
            self._call("PATCH", f"/crm/v3/objects/companies/{existing}",
                       json={"properties": props})
            return existing
        return self._call("POST", "/crm/v3/objects/companies",
                          json={"properties": props})["id"]

    def upsert_contact(self, contact: Contact, company_id: str,
                       owner_id: str) -> str:
        props = {
            "email": contact.email.lower(),
            "firstname": contact.first_name,
            "lastname": contact.last_name,
            "jobtitle": contact.title,
            "hubspot_owner_id": owner_id,
            "hs_lead_status": "NEW",
        }
        props = {k: v for k, v in props.items() if v not in ("", None)}
        existing = self.find_contact(contact.email)
        if existing:
            self._call("PATCH", f"/crm/v3/objects/contacts/{existing}",
                       json={"properties": props})
            contact_id = existing
        else:
            contact_id = self._call("POST", "/crm/v3/objects/contacts",
                                    json={"properties": props})["id"]
        if company_id:
            self.associate("contacts", contact_id, "companies", company_id, 1)
        return contact_id

    def create_deal(self, *, name: str, pipeline: str, stage: str, owner_id: str,
                    amount: Optional[float], close_date_ms: Optional[int],
                    company_id: str = "", contact_id: str = "",
                    description: str = "") -> str:
        props: dict[str, Any] = {
            "dealname": name,
            "pipeline": pipeline,
            "dealstage": stage,
            "hubspot_owner_id": owner_id,
            "dealtype": "newbusiness",
        }
        if amount is not None:
            props["amount"] = str(amount)
        if close_date_ms:
            props["closedate"] = str(close_date_ms)
        if description:
            props["description"] = description
        deal_id = self._call("POST", "/crm/v3/objects/deals",
                             json={"properties": props})["id"]
        if company_id:
            self.associate("deals", deal_id, "companies", company_id, 5)
        if contact_id:
            self.associate("deals", deal_id, "contacts", contact_id, 3)
        return deal_id

    def update_deal_stage(self, deal_id: str, stage: str) -> None:
        self._call("PATCH", f"/crm/v3/objects/deals/{deal_id}",
                   json={"properties": {"dealstage": stage}})

    def find_deal_for_company(self, company_id: str, name_prefix: str) -> Optional[str]:
        body = {
            "filterGroups": [{"filters": [
                {"propertyName": "associations.company", "operator": "EQ",
                 "value": company_id},
                {"propertyName": "dealname", "operator": "CONTAINS_TOKEN",
                 "value": name_prefix},
            ]}],
            "properties": ["dealname", "dealstage"],
            "limit": 1,
        }
        try:
            results = self._call("POST", "/crm/v3/objects/deals/search",
                                 json=body).get("results", [])
        except requests.HTTPError:
            return None
        return results[0]["id"] if results else None

    def log_note(self, body: str, contact_id: str = "", company_id: str = "",
                 deal_id: str = "", timestamp_ms: Optional[int] = None) -> str:
        import time
        props = {
            "hs_note_body": body,
            "hs_timestamp": str(timestamp_ms or int(time.time() * 1000)),
        }
        note_id = self._call("POST", "/crm/v3/objects/notes",
                             json={"properties": props})["id"]
        for obj_type, obj_id, type_id in (
            ("contacts", contact_id, 202),
            ("companies", company_id, 190),
            ("deals", deal_id, 214),
        ):
            if obj_id:
                self.associate("notes", note_id, obj_type, obj_id, type_id)
        return note_id

    def associate(self, from_type: str, from_id: str, to_type: str,
                  to_id: str, type_id: int) -> None:
        try:
            self._call(
                "PUT",
                f"/crm/v4/objects/{from_type}/{from_id}/associations/{to_type}/{to_id}",
                json=[{"associationCategory": "HUBSPOT_DEFINED",
                       "associationTypeId": type_id}],
            )
        except requests.HTTPError:
            # A missing association is not worth failing an entire sync over.
            log.warning("Could not associate %s/%s -> %s/%s",
                        from_type, from_id, to_type, to_id)


def sync_property(client: HubSpotClient, cfg: Config, store,
                  prop: Property, create_deal: bool = True) -> dict[str, str]:
    """Push one property, its contacts, and an open vending deal into HubSpot."""
    hs = cfg.hubspot
    owner_id = str(hs["owner_id"])

    company_id = client.upsert_company(prop, owner_id)
    store.update_property(prop.key, hubspot_company_id=company_id)

    contact_ids: list[str] = []
    for contact in store.contacts_for(prop.key):
        cid = client.upsert_contact(contact, company_id, owner_id)
        store.update_contact(contact.email, hubspot_contact_id=cid)
        contact_ids.append(cid)

    deal_id = ""
    if create_deal:
        deal_id = client.find_deal_for_company(company_id, hs["deal_name_prefix"]) or ""
        if not deal_id:
            deal_id = client.create_deal(
                name=f"{hs['deal_name_prefix']} - {prop.name}",
                pipeline=hs["pipeline"],
                stage=hs["stage_new"],
                owner_id=owner_id,
                amount=float(cfg.offer["sales_guarantee_usd"]),
                close_date_ms=None,
                company_id=company_id,
                contact_id=contact_ids[0] if contact_ids else "",
                description=(
                    f"Auto-sourced resident vending target.\n"
                    f"Fit score: {prop.score}/100\n"
                    f"Signals: {prop.score_reasons}\n"
                    f"Units: {prop.unit_count or 'unknown'}\n"
                    f"Management: {prop.management_company or 'unknown'}"
                ),
            )
    store.conn.commit()
    return {"company_id": company_id, "deal_id": deal_id,
            "contact_ids": ",".join(contact_ids)}
