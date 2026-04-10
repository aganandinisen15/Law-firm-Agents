from __future__ import annotations

from typing import Dict, Any, List, Optional
import base64
import hashlib
import logging
import json
from email.utils import parseaddr

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from shared.legal_agents.settings import settings

logger = logging.getLogger(__name__)


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


class AnthropicAdapter:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def summarize(self, prompt: str) -> Dict[str, Any]:
        return {"model": self.model, "content": prompt[:500]}

    def json_completion(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")

        from anthropic import Anthropic

        client = Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=1200,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text_parts: List[str] = []
        for block in response.content:
            block_text = getattr(block, "text", None)
            if block_text:
                text_parts.append(block_text)
        raw = "".join(text_parts).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("Anthropic response was not valid JSON: %s", raw)
            raise RuntimeError("Claude returned non-JSON content") from exc


class GoogleWorkspaceAdapter:
    GMAIL_SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.compose",
    ]

    def is_gmail_configured(self) -> bool:
        return bool(
            settings.google_client_id
            and settings.google_client_secret
            and settings.google_refresh_token
        )

    def _gmail_service(self):
        if not self.is_gmail_configured():
            raise RuntimeError(
                "Gmail is not configured. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN."
            )

        creds = Credentials(
            token=None,
            refresh_token=settings.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=self.GMAIL_SCOPES,
        )
        creds.refresh(Request())
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    @staticmethod
    def _decode_body(data: Optional[str]) -> str:
        if not data:
            return ""
        try:
            return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _extract_plain_text(self, payload: Dict[str, Any]) -> str:
        mime_type = payload.get("mimeType", "")
        body = payload.get("body", {}) or {}
        data = body.get("data")
        if mime_type == "text/plain" and data:
            return self._decode_body(data)

        for part in payload.get("parts", []) or []:
            text = self._extract_plain_text(part)
            if text:
                return text

        if data:
            return self._decode_body(data)
        return ""

    def _headers_to_map(self, headers: List[Dict[str, Any]]) -> Dict[str, str]:
        return {str(h.get("name", "")).lower(): str(h.get("value", "")) for h in headers or []}

    def _normalize_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("payload", {}) or {}
        headers = self._headers_to_map(payload.get("headers", []))
        from_header = headers.get("from", "")
        sender_email = parseaddr(from_header)[1] or from_header
        attachments = [p for p in payload.get("parts", []) or [] if p.get("filename")]
        snippet = message.get("snippet", "")
        body = self._extract_plain_text(payload) or snippet
        labels = message.get("labelIds", []) or []
        return {
            "gmail_message_id": message.get("id"),
            "thread_id": message.get("threadId"),
            "from": sender_email,
            "from_display": from_header,
            "subject": headers.get("subject", ""),
            "body": body,
            "snippet": snippet,
            "has_attachments": bool(attachments),
            "attachments": [
                {"filename": part.get("filename"), "mimeType": part.get("mimeType", "")}
                for part in attachments
            ],
            "received_at": headers.get("date", ""),
            "label_ids": labels,
            "is_unread": "UNREAD" in labels,
        }

    def list_inbox_messages(self, max_results: int = 10, query: str = "") -> Dict[str, Any]:
        service = self._gmail_service()
        gmail_query = query or settings.gmail_default_query or "in:inbox"
        response = service.users().messages().list(
            userId=settings.gmail_mailbox_user,
            maxResults=max_results,
            q=gmail_query,
        ).execute()
        refs = response.get("messages", [])
        items: List[Dict[str, Any]] = []
        for ref in refs:
            full = service.users().messages().get(
                userId=settings.gmail_mailbox_user,
                id=ref["id"],
                format="full",
            ).execute()
            items.append(self._normalize_message(full))
        return {"configured": True, "items": items, "query": gmail_query}

    def get_message(self, message_id: str) -> Dict[str, Any]:
        service = self._gmail_service()
        full = service.users().messages().get(
            userId=settings.gmail_mailbox_user,
            id=message_id,
            format="full",
        ).execute()
        return self._normalize_message(full)

    def check_calendar(self, attendees: List[Dict[str, str]], proposed_times: List[str]) -> Dict[str, Any]:
        return {"available": proposed_times[:1], "conflicts": proposed_times[1:]}

    def create_event(self, title: str, when: str, attendees: List[Dict[str, str]]) -> Dict[str, Any]:
        return {"calendar_event_id": stable_hash(title + when), "title": title, "when": when, "attendees": attendees}

    def _ensure_label(self, service, label_name: str) -> Optional[str]:
        labels = service.users().labels().list(userId=settings.gmail_mailbox_user).execute().get("labels", [])
        for label in labels:
            if label.get("name") == label_name:
                return label.get("id")
        created = service.users().labels().create(
            userId=settings.gmail_mailbox_user,
            body={
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        ).execute()
        return created.get("id")

    def apply_label(self, message_id: str, label_name: str) -> Dict[str, Any]:
        if not self.is_gmail_configured():
            return {"message_id": message_id, "label_name": label_name, "status": "stubbed"}
        try:
            service = self._gmail_service()
            label_id = self._ensure_label(service, label_name)
            service.users().messages().modify(
                userId=settings.gmail_mailbox_user,
                id=message_id,
                body={"addLabelIds": [label_id]},
            ).execute()
            return {"message_id": message_id, "label_name": label_name, "status": "applied"}
        except HttpError as exc:
            logger.warning("apply_label failed, falling back to stub: %s", exc)
            return {"message_id": message_id, "label_name": label_name, "status": "stubbed", "warning": str(exc)}

    def star_message(self, message_id: str) -> Dict[str, Any]:
        if not self.is_gmail_configured():
            return {"message_id": message_id, "status": "stubbed"}
        try:
            service = self._gmail_service()
            service.users().messages().modify(
                userId=settings.gmail_mailbox_user,
                id=message_id,
                body={"addLabelIds": ["STARRED"]},
            ).execute()
            return {"message_id": message_id, "status": "starred"}
        except HttpError as exc:
            logger.warning("star_message failed, falling back to stub: %s", exc)
            return {"message_id": message_id, "status": "stubbed", "warning": str(exc)}

    def archive_message(self, message_id: str) -> Dict[str, Any]:
        if not self.is_gmail_configured():
            return {"message_id": message_id, "status": "stubbed"}
        try:
            service = self._gmail_service()
            service.users().messages().modify(
                userId=settings.gmail_mailbox_user,
                id=message_id,
                body={"removeLabelIds": ["INBOX"]},
            ).execute()
            return {"message_id": message_id, "status": "archived"}
        except HttpError as exc:
            logger.warning("archive_message failed, falling back to stub: %s", exc)
            return {"message_id": message_id, "status": "stubbed", "warning": str(exc)}

    def send_sms_alert(self, body: str) -> Dict[str, Any]:
        if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number and settings.alert_sms_to):
            return {"status": "stubbed", "body_preview": body[:160]}
        try:
            import httpx
            response = httpx.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
                data={
                    "From": settings.twilio_from_number,
                    "To": settings.alert_sms_to,
                    "Body": body,
                },
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            return {"status": "sent", "sid": payload.get("sid"), "body_preview": body[:160]}
        except Exception as exc:
            logger.warning("send_sms_alert failed, falling back to stub: %s", exc)
            return {"status": "stubbed", "warning": str(exc), "body_preview": body[:160]}

    def create_draft(self, to_email: str, subject: str, body: str, thread_id: Optional[str] = None) -> Dict[str, Any]:
        if not self.is_gmail_configured():
            seed = f"{to_email}|{subject}|{thread_id or ''}"
            return {
                "draft_id": f"draft_{stable_hash(seed)}",
                "to": to_email,
                "subject": subject,
                "body_preview": body[:160],
                "thread_id": thread_id,
                "status": "stubbed",
            }

        from email.message import EmailMessage

        message = EmailMessage()
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        body_payload: Dict[str, Any] = {"message": {"raw": encoded_message}}
        if thread_id:
            body_payload["message"]["threadId"] = thread_id

        service = self._gmail_service()
        created = service.users().drafts().create(
            userId=settings.gmail_mailbox_user,
            body=body_payload,
        ).execute()
        draft = created.get("message", {})
        return {
            "draft_id": created.get("id"),
            "to": to_email,
            "subject": subject,
            "body_preview": body[:160],
            "thread_id": draft.get("threadId", thread_id),
            "status": "created_in_gmail",
        }


class LexisNexisAdapter:
    def search_cases(self, query: str, jurisdiction: str) -> List[Dict[str, Any]]:
        return [{
            "case_id": stable_hash(query + jurisdiction),
            "citation": "123 Cal.App.4th 456",
            "case_name": "Sample LLC v. Example Member",
            "jurisdiction": jurisdiction,
            "relevance_score": 8
        }]

    def pull_case(self, case_id: str) -> Dict[str, Any]:
        return {
            "case_id": case_id,
            "citation": "123 Cal.App.4th 456",
            "case_name": "Sample LLC v. Example Member",
            "full_text": "An LLC operating agreement may restrict member voting rights when consistent with the governing statute.",
            "headnotes": "Sample headnote for development only.",
            "page_number": "461",
        }

    def shepardize(self, citation: str) -> Dict[str, Any]:
        return {"citation": citation, "status": "good_law", "negative_treatment": False}
