"""Credential and environment checks.

Every stage degrades independently: no Places key just means no new discovery,
no Gmail just means no sending. `doctor` reports what is live and what each
missing piece costs, so a Replit run never fails halfway with a vague error.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .config import Config


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    unlocks: str

    @property
    def mark(self) -> str:
        return "OK  " if self.ok else "MISS"


def _mask(value: str) -> str:
    if not value:
        return "(unset)"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]} ({len(value)} chars)"


def on_replit() -> bool:
    return bool(os.getenv("REPL_ID") or os.getenv("REPLIT_DEPLOYMENT")
                or os.getenv("REPLIT_DEV_DOMAIN"))


def check_places(cfg: Config) -> Check:
    key = cfg.secrets.places_api_key
    return Check("GOOGLE_PLACES_API_KEY", bool(key), _mask(key),
                 "discovering new apartment communities")


def check_google_oauth(cfg: Config) -> Check:
    cid = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    csec = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    rtok = os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN", "")
    if cid and csec and rtok:
        return Check("Google OAuth (env)", True, f"refresh token {_mask(rtok)}",
                     "reading the calendar, drafting and sending mail")
    from pathlib import Path
    cache = Path(cfg.secrets.google_token_cache)
    if cache.exists():
        return Check("Google OAuth (token file)", True, str(cache),
                     "reading the calendar, drafting and sending mail")
    missing = [n for n, v in (("CLIENT_ID", cid), ("CLIENT_SECRET", csec),
                              ("REFRESH_TOKEN", rtok)) if not v]
    return Check("Google OAuth", False, f"missing {', '.join(missing)}",
                 "reading the calendar, drafting and sending mail")


def check_database(cfg: Config) -> Check:
    url = os.getenv("DATABASE_URL", "")
    if url:
        host = url.split("@")[-1].split("/")[0] if "@" in url else "configured"
        return Check("DATABASE_URL", True, f"Postgres at {host}",
                     "remembering who was already contacted")
    detail = "not set -- using a local SQLite file"
    if on_replit():
        detail = ("not set. On a Scheduled Deployment the filesystem is wiped "
                  "between runs, so SQLite will re-contact everyone")
    return Check("DATABASE_URL", not on_replit(), detail,
                 "remembering who was already contacted")


def check_sender(cfg: Config) -> Check:
    email = cfg.secrets.sender_email
    return Check("SENDER_EMAIL", bool(email), email or "(unset)",
                 "outreach (no From address)")


def check_crm(cfg: Config) -> list[Check]:
    out: list[Check] = []
    crm = cfg.raw.get("crm", {})
    primary = crm.get("primary", "none")
    if primary == "replit":
        base = os.getenv("CRM_BASE_URL", "") or crm.get("replit", {}).get("base_url", "")
        token = os.getenv("CRM_API_TOKEN", "")
        out.append(Check("CRM_BASE_URL", bool(base), base or "(unset)",
                         "syncing targets into your Replit CRM"))
        out.append(Check("CRM_API_TOKEN", bool(token), _mask(token),
                         "authenticating to your Replit CRM"))
    if crm.get("hubspot", {}).get("enabled"):
        tok = cfg.secrets.hubspot_token
        out.append(Check("HUBSPOT_ACCESS_TOKEN", bool(tok), _mask(tok),
                         "mirroring contacts into HubSpot (secondary)"))
    return out


def run_checks(cfg: Config) -> list[Check]:
    checks = [check_database(cfg), check_google_oauth(cfg), check_places(cfg),
              check_sender(cfg)]
    checks.extend(check_crm(cfg))
    return checks


def render(checks: list[Check], cfg: Config) -> str:
    lines = ["", f"Environment: {'Replit' if on_replit() else 'local'}", ""]
    width = max(len(c.name) for c in checks)
    for c in checks:
        lines.append(f"  [{c.mark}] {c.name.ljust(width)}  {c.detail}")
    missing = [c for c in checks if not c.ok]
    if missing:
        lines += ["", "Missing, and what each one costs you:", ""]
        for c in missing:
            lines.append(f"  - {c.name}\n      without it: no {c.unlocks}")
    else:
        lines += ["", "All configured."]
    lines.append("")
    return "\n".join(lines)
