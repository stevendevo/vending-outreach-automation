#!/usr/bin/env bash
# One-time setup.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

[ -f .env ] || { cp .env.example .env; echo "Created .env -- fill it in."; }
mkdir -p secrets data

echo
echo "Next:"
echo "  1. Fill in .env (Places key, HubSpot token, sender email)."
echo "  2. Drop your Google OAuth desktop-client JSON at secrets/google_client_secret.json"
echo "  3. Authorize once:  PYTHONPATH=src python -m vending_outreach slots"
echo "  4. Dry run:         PYTHONPATH=src python -m vending_outreach outreach --mode dry-run --show-bodies"
