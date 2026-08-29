"""Configuration loading. One YAML file plus a .env for secrets."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "config.yaml"


@dataclass
class Secrets:
    places_api_key: str = ""
    hubspot_token: str = ""
    google_client_secrets: str = ""
    google_token_cache: str = ""
    sender_email: str = ""

    @classmethod
    def from_env(cls) -> "Secrets":
        load_dotenv(REPO_ROOT / ".env")
        return cls(
            places_api_key=os.getenv("GOOGLE_PLACES_API_KEY", ""),
            hubspot_token=os.getenv("HUBSPOT_ACCESS_TOKEN", ""),
            google_client_secrets=os.getenv(
                "GOOGLE_OAUTH_CLIENT_SECRETS", "./secrets/google_client_secret.json"
            ),
            google_token_cache=os.getenv(
                "GOOGLE_OAUTH_TOKEN_CACHE", "./secrets/google_token.json"
            ),
            sender_email=os.getenv("SENDER_EMAIL", ""),
        )

    def require(self, *names: str) -> None:
        """Fail loudly and early rather than half-way through a run."""
        missing = [n for n in names if not getattr(self, n)]
        if missing:
            raise SystemExit(
                "Missing credentials: "
                + ", ".join(missing)
                + "\nCopy .env.example to .env and fill these in."
            )


@dataclass
class Config:
    raw: dict[str, Any]
    path: Path
    secrets: Secrets = field(default_factory=Secrets.from_env)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        p = Path(path) if path else DEFAULT_CONFIG
        with open(p) as fh:
            raw = yaml.safe_load(fh)
        return cls(raw=raw, path=p)

    # Thin accessors so call sites read like prose.
    @property
    def business(self) -> dict: return self.raw["business"]
    @property
    def offer(self) -> dict: return self.raw["offer"]
    @property
    def discovery(self) -> dict: return self.raw["discovery"]
    @property
    def scoring(self) -> dict: return self.raw["scoring"]
    @property
    def calendar(self) -> dict: return self.raw["calendar"]
    @property
    def outreach(self) -> dict: return self.raw["outreach"]
    @property
    def hubspot(self) -> dict: return self.raw["hubspot"]

    def suppression(self) -> set[str]:
        """Lowercased emails and bare domains we must never contact."""
        rel = self.outreach.get("suppression_file")
        if not rel:
            return set()
        p = REPO_ROOT / rel
        if not p.exists():
            return set()
        out: set[str] = set()
        for line in p.read_text().splitlines():
            line = line.split("#", 1)[0].strip().lower()
            if line:
                out.add(line)
        return out
