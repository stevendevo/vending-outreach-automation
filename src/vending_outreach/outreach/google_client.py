"""Gmail + Calendar access under one OAuth session.

Gmail is used three ways: create drafts (the safe default), send, and check for
inbound replies so a sequence stops the moment a human answers.
"""
from __future__ import annotations

import base64
import logging
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def get_credentials(client_secrets: str, token_cache: str) -> Credentials:
    cache = Path(token_cache)
    creds: Optional[Credentials] = None
    if cache.exists():
        creds = Credentials.from_authorized_user_file(str(cache), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        secrets = Path(client_secrets)
        if not secrets.exists():
            raise SystemExit(
                f"Google OAuth client secrets not found at {secrets}.\n"
                "Create a Desktop-app OAuth client in Google Cloud, download the "
                "JSON, and point GOOGLE_OAUTH_CLIENT_SECRETS at it."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
        creds = flow.run_local_server(port=0)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(creds.to_json())
    return creds


class GoogleClient:
    def __init__(self, client_secrets: str, token_cache: str, sender: str):
        self.creds = get_credentials(client_secrets, token_cache)
        self.sender = sender
        self._gmail = None
        self._calendar = None

    @property
    def gmail(self):
        if self._gmail is None:
            self._gmail = build("gmail", "v1", credentials=self.creds,
                                cache_discovery=False)
        return self._gmail

    @property
    def calendar(self):
        if self._calendar is None:
            self._calendar = build("calendar", "v3", credentials=self.creds,
                                   cache_discovery=False)
        return self._calendar

    # ------------------------------------------------------------------- gmail
    def _raw(self, to: str, subject: str, body: str,
             thread_id: str = "") -> dict:
        msg = MIMEText(body, "plain", "utf-8")
        msg["To"] = to
        msg["From"] = self.sender
        msg["Subject"] = subject
        payload = {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}
        if thread_id:
            payload["threadId"] = thread_id
        return payload

    def create_draft(self, to: str, subject: str, body: str,
                     thread_id: str = "") -> dict:
        draft = self.gmail.users().drafts().create(
            userId="me", body={"message": self._raw(to, subject, body, thread_id)}
        ).execute()
        return {
            "message_id": draft.get("message", {}).get("id", ""),
            "thread_id": draft.get("message", {}).get("threadId", ""),
            "draft_id": draft.get("id", ""),
        }

    def send(self, to: str, subject: str, body: str, thread_id: str = "") -> dict:
        sent = self.gmail.users().messages().send(
            userId="me", body=self._raw(to, subject, body, thread_id)
        ).execute()
        return {"message_id": sent.get("id", ""), "thread_id": sent.get("threadId", "")}

    def has_reply_from(self, email: str, after_iso: str = "") -> bool:
        """True if this address has written to us (not us to them)."""
        query = f"from:{email} -in:sent -in:draft"
        if after_iso:
            query += f" after:{after_iso[:10].replace('-', '/')}"
        resp = self.gmail.users().messages().list(
            userId="me", q=query, maxResults=1
        ).execute()
        return bool(resp.get("messages"))

    # ---------------------------------------------------------------- calendar
    def list_events(self, calendar_id: str, time_min_iso: str,
                    time_max_iso: str) -> list[dict]:
        events: list[dict] = []
        page_token = None
        while True:
            resp = self.calendar.events().list(
                calendarId=calendar_id, timeMin=time_min_iso, timeMax=time_max_iso,
                singleEvents=True, orderBy="startTime", maxResults=250,
                pageToken=page_token,
            ).execute()
            events.extend(resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                return events
