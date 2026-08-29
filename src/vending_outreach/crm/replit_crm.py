"""Adapter for the Replit-hosted Grilly Cheese CRM.

The CRM lives on the same server as grillycheese.net. Its exact routes and
field names are configured in `config.yaml` under `crm.replit` rather than
hard-coded, so the endpoints can be pointed at whatever the backend actually
exposes without touching this file.

Run `vending-outreach sync --preview` to print the exact JSON this would POST;
that payload is what the CRM endpoint needs to accept.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import requests

from .base import ActivityPayload, LeadPayload

log = logging.getLogger(__name__)


class ReplitCRMClient:
    name = "replit"

    def __init__(self, base_url: str, token: str = "", *,
                 endpoints: Optional[dict] = None,
                 field_map: Optional[dict] = None,
                 auth_scheme: str = "bearer",
                 auth_header: str = "Authorization",
                 timeout: int = 30,
                 session: Optional[requests.Session] = None):
        if not base_url:
            raise SystemExit(
                "No CRM base URL. Set CRM_BASE_URL as a Replit Secret, or "
                "crm.replit.base_url in config.yaml."
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.endpoints = endpoints or {}
        self.field_map = field_map or {}
        self.session = session or requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        if token:
            value = f"Bearer {token}" if auth_scheme == "bearer" else token
            self.session.headers[auth_header] = value

    # ------------------------------------------------------------------ util
    def _map(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Rename our neutral keys onto the CRM's own field names."""
        if not self.field_map:
            return payload
        return {self.field_map.get(k, k): v for k, v in payload.items()}

    def _route(self, key: str, default: str) -> tuple[str, str]:
        """`"POST /api/leads"` -> ("POST", "/api/leads")."""
        spec = self.endpoints.get(key, default)
        method, _, path = spec.partition(" ")
        return method.upper().strip(), path.strip()

    def _call(self, method: str, path: str, body: dict) -> dict:
        url = f"{self.base_url}{path}"
        resp = self.session.request(method, url, json=body, timeout=self.timeout)
        if resp.status_code >= 400:
            log.error("CRM %s %s -> %s: %s", method, url, resp.status_code,
                      resp.text[:400])
            resp.raise_for_status()
        try:
            return resp.json() if resp.text else {}
        except ValueError:
            return {"raw": resp.text}

    # --------------------------------------------------------------- adapter
    def upsert_lead(self, lead: LeadPayload) -> str:
        method, path = self._route("upsert_lead", "POST /api/crm/leads")
        body = self._map(lead.to_dict())
        data = self._call(method, path, body)
        return str(data.get("id") or data.get("lead_id") or lead.external_id)

    def log_activity(self, activity: ActivityPayload) -> str:
        method, path = self._route("log_activity", "POST /api/crm/activities")
        body = self._map(activity.to_dict())
        data = self._call(method, path, body)
        return str(data.get("id") or "")


class PreviewCRMClient:
    """Prints what it would send instead of sending it.

    Used by `sync --preview` so the exact contract can be handed to whoever is
    building the CRM endpoint, before any live call is made.
    """
    name = "preview"

    def __init__(self, base_url: str = "", endpoints: Optional[dict] = None, **kw):
        self.base_url = base_url or "https://<your-crm>"
        self.endpoints = endpoints or {}
        self.calls: list[dict] = []

    def _record(self, key: str, default: str, body: dict) -> str:
        spec = self.endpoints.get(key, default)
        method, _, path = spec.partition(" ")
        entry = {"method": method, "url": f"{self.base_url}{path}", "body": body}
        self.calls.append(entry)
        print(f"\n{method} {self.base_url}{path}")
        print(json.dumps(body, indent=2, sort_keys=True))
        return "preview"

    def upsert_lead(self, lead: LeadPayload) -> str:
        return self._record("upsert_lead", "POST /api/crm/leads", lead.to_dict())

    def log_activity(self, activity: ActivityPayload) -> str:
        return self._record("log_activity", "POST /api/crm/activities",
                            activity.to_dict())
