"""CRM sink resolution.

`crm.primary` in config.yaml decides where leads land; `crm.hubspot.enabled`
decides whether contacts are also mirrored into HubSpot.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from ..config import Config

log = logging.getLogger(__name__)
from .base import ActivityPayload, CRMAdapter, LeadPayload, lead_from


def build_primary(cfg: Config, store, preview: bool = False) -> Optional[CRMAdapter]:
    crm = cfg.raw.get("crm", {})
    primary = crm.get("primary", "none")

    if primary == "replit":
        from .replit_crm import PreviewCRMClient, ReplitCRMClient
        settings = crm.get("replit", {}) or {}
        base_url = os.getenv("CRM_BASE_URL", "") or settings.get("base_url", "")
        token = os.getenv("CRM_API_TOKEN", "") or settings.get("token", "")
        kwargs = dict(
            endpoints=settings.get("endpoints", {}),
            field_map=settings.get("field_map", {}),
            auth_scheme=settings.get("auth_scheme", "bearer"),
            auth_header=settings.get("auth_header", "Authorization"),
        )
        if preview:
            return PreviewCRMClient(base_url=base_url,
                                    endpoints=kwargs["endpoints"])
        if not base_url:
            # A nightly run must not die here -- emails may already have gone
            # out. Report it and let the rest of the pass finish.
            log.warning(
                "CRM sync skipped: no base URL. Set the CRM_BASE_URL secret "
                "(or crm.replit.base_url) to enable it."
            )
            return None
        return ReplitCRMClient(base_url, token, **kwargs)

    if primary == "hubspot":
        return build_hubspot(cfg, store, contacts_only=False)

    return None


def build_hubspot(cfg: Config, store, contacts_only: bool = True) -> Optional[CRMAdapter]:
    settings = cfg.raw.get("crm", {}).get("hubspot", {}) or {}
    if not settings.get("enabled"):
        return None
    if not cfg.secrets.hubspot_token:
        return None
    from .hubspot import HubSpotAdapter, HubSpotClient
    return HubSpotAdapter(HubSpotClient(cfg.secrets.hubspot_token), cfg, store,
                          contacts_only=contacts_only)


__all__ = ["ActivityPayload", "CRMAdapter", "LeadPayload", "lead_from",
           "build_primary", "build_hubspot"]
