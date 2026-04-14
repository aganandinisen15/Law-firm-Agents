from __future__ import annotations

from datetime import datetime, timedelta
import base64
import json
import os
from typing import Any

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except Exception:  # pragma: no cover
    Credentials = None
    Request = None
    build = None


CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.compose",
]


class GoogleWorkspaceClients:
    def __init__(self, enabled: bool, calendar_service: Any = None, gmail_service: Any = None, calendar_id: str = "primary"):
        self.enabled = enabled
        self.calendar_service = calendar_service
        self.gmail_service = gmail_service
        self.calendar_id = calendar_id

    @classmethod
    def from_env(cls) -> "GoogleWorkspaceClients":
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
        calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")

        if not all([client_id, client_secret, refresh_token]) or Credentials is None:
            return cls(enabled=False, calendar_id=calendar_id)

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=CALENDAR_SCOPES,
        )
        creds.refresh(Request())
        calendar_service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        gmail_service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return cls(enabled=True, calendar_service=calendar_service, gmail_service=gmail_service, calendar_id=calendar_id)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "calendar_id": self.calendar_id,
            "mode": "google_api" if self.enabled else "fallback",
        }

    def is_time_available(self, start_dt: datetime, end_dt: datetime) -> bool:
        if not self.enabled:
            # deterministic local fallback: block lunch and one afternoon slot
            if 12 <= start_dt.hour < 14:
                return False
            if start_dt.weekday() == 1 and start_dt.hour == 14:
                return False
            return True

        window_start = (start_dt - timedelta(minutes=30)).isoformat() + "Z"
        window_end = (end_dt + timedelta(minutes=30)).isoformat() + "Z"
        events = self.calendar_service.events().list(
            calendarId=self.calendar_id,
            timeMin=window_start,
            timeMax=window_end,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        return len(events.get("items", [])) == 0

    def create_calendar_event(
        self,
        title: str,
        start_iso: str,
        end_iso: str,
        attendees: list[str],
        location: str,
        notes: str,
        add_video: bool,
    ) -> str:
        if not self.enabled:
            return f"local-event-{start_iso}"

        body: dict[str, Any] = {
            "summary": title,
            "location": location,
            "description": notes,
            "start": {"dateTime": start_iso},
            "end": {"dateTime": end_iso},
            "attendees": [{"email": email} for email in attendees if email],
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 60},
                    {"method": "email", "minutes": 24 * 60},
                ],
            },
        }
        if add_video:
            body["conferenceData"] = {
                "createRequest": {
                    "requestId": f"meet-{start_iso}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            }
        event = self.calendar_service.events().insert(
            calendarId=self.calendar_id,
            body=body,
            conferenceDataVersion=1 if add_video else 0,
            sendUpdates="all",
        ).execute()
        return event.get("id", "")

    def create_gmail_draft(self, to: str, subject: str, body: str) -> str:
        if not to:
            return "no-recipient"
        if not self.enabled:
            return "draft-created-locally"
        message = f"To: {to}\r\nSubject: {subject}\r\n\r\n{body}"
        encoded = base64.urlsafe_b64encode(message.encode("utf-8")).decode("utf-8")
        draft = self.gmail_service.users().drafts().create(userId="me", body={"message": {"raw": encoded}}).execute()
        return draft.get("id", "")
