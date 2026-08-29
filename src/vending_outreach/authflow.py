"""One-time OAuth bootstrap.

Replit Scheduled Deployments are headless with an ephemeral filesystem, so the
usual "open a browser, cache a token file" flow does not work there. Instead you
run this once on a machine that has a browser; it prints the three values to
paste into Replit Secrets, and the deployment refreshes its own access tokens
from then on.
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import Config


def mint_refresh_token(cfg: Config) -> dict[str, str]:
    from google_auth_oauthlib.flow import InstalledAppFlow

    from .outreach.google_client import SCOPES

    secrets_path = Path(cfg.secrets.google_client_secrets)
    if not secrets_path.exists():
        raise SystemExit(
            f"Client secrets not found at {secrets_path}.\n"
            "In Google Cloud: APIs & Services > Credentials > Create "
            "credentials > OAuth client ID > Desktop app. Download the JSON "
            "and point GOOGLE_OAUTH_CLIENT_SECRETS at it."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
    # access_type=offline + prompt=consent is what actually returns a refresh
    # token; without prompt=consent Google omits it on repeat authorizations.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    if not creds.refresh_token:
        raise SystemExit(
            "Google did not return a refresh token. Revoke the app's access at "
            "https://myaccount.google.com/permissions and run this again."
        )

    data = json.loads(secrets_path.read_text())
    installed = data.get("installed") or data.get("web") or {}
    return {
        "GOOGLE_OAUTH_CLIENT_ID": installed.get("client_id", creds.client_id or ""),
        "GOOGLE_OAUTH_CLIENT_SECRET": installed.get("client_secret", creds.client_secret or ""),
        "GOOGLE_OAUTH_REFRESH_TOKEN": creds.refresh_token,
    }


def render_instructions(values: dict[str, str]) -> str:
    lines = [
        "",
        "=" * 70,
        "Add these three to your Replit Secrets (Tools > Secrets):",
        "=" * 70,
        "",
    ]
    for key, value in values.items():
        lines.append(f"{key}")
        lines.append(f"  {value}")
        lines.append("")
    lines += [
        "=" * 70,
        "Treat the refresh token like a password: it grants ongoing access to",
        "send mail as this account. Never commit it.",
        "=" * 70,
        "",
    ]
    return "\n".join(lines)
