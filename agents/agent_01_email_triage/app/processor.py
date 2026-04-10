from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from shared.legal_agents.adapters import AnthropicAdapter, GoogleWorkspaceAdapter, stable_hash
from shared.legal_agents.db import engine
from shared.legal_agents.db_utils import log_audit, log_error
from shared.legal_agents.schemas import GenericAgentRequest
from shared.legal_agents.settings import settings

logger = logging.getLogger(__name__)

AGENT_SLUG = "email_triage"
ALLOWED_CATEGORIES = {
    "URGENT_CLIENT",
    "CLIENT_ROUTINE",
    "COURT",
    "OPPOSING_COUNSEL",
    "ADMIN",
    "BUSINESS_DEV",
    "SPAM",
    "NEEDS_MANUAL_REVIEW",
}

SYSTEM_PROMPT = """You are an email categorization assistant for a law firm. Analyze emails and categorize them.
Return JSON only with this exact schema:
{
  "category": "URGENT_CLIENT|CLIENT_ROUTINE|COURT|OPPOSING_COUNSEL|ADMIN|BUSINESS_DEV|SPAM|NEEDS_MANUAL_REVIEW",
  "sentiment": "positive|neutral|negative|angry",
  "requires_response": true,
  "urgency_score": 1,
  "action_items": ["..."],
  "deadline": "YYYY-MM-DD or null",
  "key_points": "Brief summary",
  "confidence": 0.0
}
Rules:
- COURT for court filings, notices, orders, docket communications.
- URGENT_CLIENT for client emergencies or time-sensitive client matters.
- OPPOSING_COUNSEL for lawyers on the other side.
- ADMIN for billing, scheduling, or firm admin.
- SPAM for unsolicited marketing.
- If uncertain, use NEEDS_MANUAL_REVIEW.
- urgency_score must be 1 to 10.
- confidence must be 0.0 to 1.0.
"""

DRAFT_PROMPT_TEMPLATE = """You are a legal assistant drafting email responses for an attorney.
Use a professional but friendly tone. Be concise.
Never make commitments or legal conclusions. Always defer to attorney review.
Sign as 'Legal Team', not as the attorney.
Return JSON only:
{
  "draft_response": "email body only"
}

<original_email>
<from>{from_email}</from>
<subject>{subject}</subject>
<body>{body}</body>
</original_email>
<email_category>{category}</email_category>
<sender_relationship>{sender_relationship}</sender_relationship>
Guidelines:
- If scheduling request: propose 2-3 time options.
- If document request: acknowledge receipt and confirm timeline.
- If question: acknowledge and state attorney will respond with analysis.
- Keep under 200 words.
- Do not make legal conclusions.
"""


def _clean_text(value: Optional[str]) -> str:
    return (value or "").replace("\x00", " ").strip()


def _extract_date_candidates(text_value: str) -> Optional[str]:
    patterns = [
        r"\b(20\d{2}-\d{2}-\d{2})\b",
        r"\b(\d{1,2}/\d{1,2}/20\d{2})\b",
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),\s*(20\d{2})\b",
    ]
    lower = (text_value or "").lower()
    for pattern in patterns:
        match = re.search(pattern, lower)
        if not match:
            continue
        raw = match.group(0)
        if re.match(r"20\d{2}-\d{2}-\d{2}", raw):
            return raw
        if "/" in raw:
            try:
                return datetime.strptime(raw, "%m/%d/%Y").strftime("%Y-%m-%d")
            except ValueError:
                continue
        try:
            return datetime.strptime(raw.title(), "%B %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _sender_relationship(from_email: str) -> str:
    lower = from_email.lower()
    if "court" in lower or lower.endswith(".gov"):
        return "court"
    if any(token in lower for token in ["esq", "law", "counsel", "legal"]):
        return "opposing_counsel"
    return "client"


def _heuristic_categorize(payload: Dict[str, Any]) -> Dict[str, Any]:
    from_email = _clean_text(payload.get("from") or payload.get("sender"))
    subject = _clean_text(payload.get("subject"))
    body = _clean_text(payload.get("body"))
    combined = f"{subject}\n{body}".lower()

    court_hits = ["court", "order", "notice", "hearing", "filing", "docket", "judge", "summons"]
    urgent_hits = ["urgent", "emergency", "asap", "immediately", "today", "tomorrow", "deadline"]
    opposing_hits = ["opposing counsel", "counsel for", "plaintiff", "defendant", "our client", "representing"]
    admin_hits = ["invoice", "billing", "payment", "schedule", "calendar", "meeting", "availability"]
    bizdev_hits = ["looking to hire", "new matter", "referral", "consultation", "engagement"]
    spam_hits = ["unsubscribe", "marketing", "newsletter", "limited offer", "seo", "sales demo"]

    category = "CLIENT_ROUTINE"
    sentiment = "neutral"
    urgency_score = 4

    if any(hit in combined for hit in spam_hits):
        category = "SPAM"
        urgency_score = 1
    elif any(hit in combined for hit in court_hits) or from_email.endswith(".gov"):
        category = "COURT"
        urgency_score = 8
    elif any(hit in combined for hit in opposing_hits):
        category = "OPPOSING_COUNSEL"
        urgency_score = 6
    elif any(hit in combined for hit in admin_hits):
        category = "ADMIN"
        urgency_score = 3
    elif any(hit in combined for hit in bizdev_hits):
        category = "BUSINESS_DEV"
        urgency_score = 5

    if any(hit in combined for hit in urgent_hits):
        if category in {"CLIENT_ROUTINE", "BUSINESS_DEV"}:
            category = "URGENT_CLIENT"
        urgency_score = max(urgency_score, 9)

    if any(word in combined for word in ["angry", "upset", "frustrated", "disappointed"]):
        sentiment = "negative"
    if any(word in combined for word in ["furious", "unacceptable", "immediately respond"]):
        sentiment = "angry"

    action_items: List[str] = []
    if "review" in combined or "attached" in combined:
        action_items.append("Review the email and any referenced documents")
    if "call" in combined or "meeting" in combined or "availability" in combined:
        action_items.append("Coordinate follow-up communication or scheduling")
    if category == "COURT":
        action_items.append("Open deadline tracking review")
    if not action_items and category != "SPAM":
        action_items.append("Attorney review")

    requires_response = category != "SPAM"
    deadline = _extract_date_candidates(combined)
    key_points = (body or subject)[:240] or "No body content supplied."
    confidence = 0.62 if category != "SPAM" else 0.9

    if category == "CLIENT_ROUTINE" and len(body) < 10:
        category = "NEEDS_MANUAL_REVIEW"
        confidence = 0.4

    return {
        "category": category,
        "sentiment": sentiment,
        "requires_response": requires_response,
        "urgency_score": urgency_score,
        "action_items": action_items,
        "deadline": deadline,
        "key_points": key_points,
        "confidence": confidence,
        "reasoning": "heuristic_fallback",
    }


def _generate_heuristic_draft(payload: Dict[str, Any], categorization: Dict[str, Any]) -> str:
    subject = _clean_text(payload.get("subject"))
    body = _clean_text(payload.get("body"))
    relationship = _sender_relationship(_clean_text(payload.get("from") or payload.get("sender")))

    if categorization["category"] == "COURT":
        return (
            "Thank you for your message. We have received the court communication and routed it for attorney review. "
            "Our team will review any required next steps and follow up as needed.\n\nLegal Team"
        )
    if any(word in f"{subject} {body}".lower() for word in ["schedule", "meeting", "availability", "call"]):
        return (
            "Thank you for your email. We received your scheduling request and will review availability. "
            "At the moment, tentative options are tomorrow at 10:00 AM, tomorrow at 2:00 PM, or the following business day at 11:30 AM. "
            "We will confirm after attorney review.\n\nLegal Team"
        )
    if "document" in body.lower() or "attached" in body.lower():
        return (
            "Thank you for sending this over. We have received the materials and routed them for attorney review. "
            "We will follow up on timing after the attorney has had an opportunity to review them.\n\nLegal Team"
        )
    if relationship == "client":
        return (
            "Thank you for your email. We have received your message and shared it for attorney review. "
            "The attorney will follow up after reviewing the issue.\n\nLegal Team"
        )
    return "Thank you for your email. We acknowledge receipt and will follow up after attorney review.\n\nLegal Team"


def _call_claude_for_categorization(payload: Dict[str, Any]) -> Dict[str, Any]:
    adapter = AnthropicAdapter(settings.anthropic_api_key, settings.anthropic_model)
    user_prompt = (
        f"<email>\n"
        f"<from>{_clean_text(payload.get('from') or payload.get('sender'))}</from>\n"
        f"<subject>{_clean_text(payload.get('subject'))}</subject>\n"
        f"<body>{_clean_text(payload.get('body'))}</body>\n"
        f"<has_attachments>{bool(payload.get('attachments'))}</has_attachments>\n"
        f"</email>"
    )
    result = adapter.json_completion(SYSTEM_PROMPT, user_prompt)
    result.setdefault("confidence", 0.9)
    result["reasoning"] = "claude"
    return result


def _call_claude_for_draft(payload: Dict[str, Any], categorization: Dict[str, Any]) -> str:
    adapter = AnthropicAdapter(settings.anthropic_api_key, settings.anthropic_model)
    prompt = DRAFT_PROMPT_TEMPLATE.format(
        from_email=_clean_text(payload.get("from") or payload.get("sender")),
        subject=_clean_text(payload.get("subject")),
        body=_clean_text(payload.get("body")),
        category=categorization["category"],
        sender_relationship=_sender_relationship(_clean_text(payload.get("from") or payload.get("sender"))),
    )
    result = adapter.json_completion("Return JSON only.", prompt)
    return str(result["draft_response"]).strip()


def _persist_email_log(payload: Dict[str, Any], categorization: Dict[str, Any], draft_created: bool, email_id: str) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO email_log (
                        email_id, received_at, sender, subject, category, urgency_score,
                        requires_response, draft_created, action_items, processed_at
                    ) VALUES (
                        :email_id, NOW(), :sender, :subject, :category, :urgency_score,
                        :requires_response, :draft_created, CAST(:action_items AS JSONB), NOW()
                    )
                    ON CONFLICT (email_id) DO UPDATE SET
                        sender = EXCLUDED.sender,
                        subject = EXCLUDED.subject,
                        category = EXCLUDED.category,
                        urgency_score = EXCLUDED.urgency_score,
                        requires_response = EXCLUDED.requires_response,
                        draft_created = EXCLUDED.draft_created,
                        action_items = EXCLUDED.action_items,
                        processed_at = EXCLUDED.processed_at
                    """
                ),
                {
                    "email_id": email_id,
                    "sender": _clean_text(payload.get("from") or payload.get("sender")),
                    "subject": _clean_text(payload.get("subject")),
                    "category": categorization["category"],
                    "urgency_score": categorization["urgency_score"],
                    "requires_response": categorization["requires_response"],
                    "draft_created": draft_created,
                    "action_items": json.dumps(categorization.get("action_items", [])),
                },
            )
    except Exception as exc:  # pragma: no cover
        logger.warning("email_log insert failed: %s", exc)


def process(request: GenericAgentRequest):
    payload = request.payload
    correlation_id = request.correlation_id or stable_hash(json.dumps(payload, sort_keys=True, default=str))
    email_id = _clean_text(payload.get("email_id") or payload.get("gmail_message_id") or correlation_id)
    warnings: List[str] = []

    if not _clean_text(payload.get("subject")) and not _clean_text(payload.get("body")):
        result = {
            "summary": "Email routed to manual review because subject and body were empty.",
            "category": "NEEDS_MANUAL_REVIEW",
            "urgency_score": 5,
            "requires_response": False,
            "draft_response": "",
            "action_items": ["Manual review required"],
            "warnings": ["Missing both subject and body."],
            "confidence": 0.1,
        }
        log_error(AGENT_SLUG, correlation_id, "empty email payload", payload)
        return result

    try:
        categorization = _call_claude_for_categorization(payload) if settings.email_triage_use_claude else _heuristic_categorize(payload)
        if categorization.get("category") not in ALLOWED_CATEGORIES:
            raise ValueError("Invalid category returned")

        if float(categorization.get("confidence", 0.0)) < 0.55:
            categorization["category"] = "NEEDS_MANUAL_REVIEW"
            warnings.append("Low confidence categorization routed to manual review.")

        draft_response = ""
        draft_record: Dict[str, Any] | None = None
        if categorization.get("requires_response"):
            try:
                draft_response = _call_claude_for_draft(payload, categorization) if settings.email_triage_use_claude else _generate_heuristic_draft(payload, categorization)
            except Exception as draft_exc:
                warnings.append(f"Draft generation fallback used: {draft_exc}")
                draft_response = _generate_heuristic_draft(payload, categorization)

        google = GoogleWorkspaceAdapter()
        applied_labels: List[str] = []
        if categorization["category"] == "NEEDS_MANUAL_REVIEW":
            applied_labels.append(settings.email_triage_label_manual_review)
        else:
            applied_labels.extend([categorization["category"], settings.email_triage_label_processed])

        for label in applied_labels:
            google.apply_label(email_id, label)

        urgent_alert = categorization["urgency_score"] >= settings.email_triage_urgent_threshold
        sms_alert: Dict[str, Any] | None = None
        if urgent_alert:
            google.star_message(email_id)
            sms_alert = google.send_sms_alert(
                f"Urgent legal email: {categorization['category']} | {_clean_text(payload.get('subject'))[:90]}"
            )

        if draft_response and settings.email_triage_save_draft_stub:
            draft_record = google.create_draft(
                to_email=_clean_text(payload.get("from") or payload.get("sender")),
                subject=f"Re: {_clean_text(payload.get('subject'))}",
                body=draft_response,
                thread_id=payload.get("thread_id"),
            )
            google.apply_label(email_id, settings.email_triage_label_pending_review)

        google.archive_message(email_id)
        _persist_email_log(payload, categorization, bool(draft_record), email_id)
        log_audit(
            AGENT_SLUG,
            "processed_email",
            correlation_id,
            {
                "email_id": email_id,
                "category": categorization["category"],
                "urgent_alert": urgent_alert,
                "confidence": categorization.get("confidence"),
            },
        )

        action_routes = []
        if categorization["category"] == "COURT":
            action_routes.append("deadline_tracking")
        if categorization.get("action_items"):
            action_routes.append("task_priority")

        return {
            "summary": f"Email categorized as {categorization['category']} with urgency {categorization['urgency_score']}/10.",
            "email_id": email_id,
            "category": categorization["category"],
            "sentiment": categorization.get("sentiment", "neutral"),
            "urgency_score": categorization["urgency_score"],
            "requires_response": categorization["requires_response"],
            "draft_response": draft_response,
            "draft_record": draft_record,
            "action_items": categorization.get("action_items", []),
            "deadline": categorization.get("deadline"),
            "key_points": categorization.get("key_points"),
            "applied_labels": applied_labels,
            "urgent_alert": urgent_alert,
            "sms_alert": sms_alert,
            "suggested_routes": action_routes,
            "processor_mode": categorization.get("reasoning"),
            "confidence": categorization.get("confidence"),
            "warnings": warnings,
        }
    except Exception as exc:
        logger.exception("Email triage processing failed")
        log_error(AGENT_SLUG, correlation_id, str(exc), payload)
        GoogleWorkspaceAdapter().apply_label(email_id, settings.email_triage_label_manual_review)
        return {
            "summary": "Email processing failed and has been routed to manual review.",
            "email_id": email_id,
            "category": "NEEDS_MANUAL_REVIEW",
            "urgency_score": 5,
            "requires_response": False,
            "draft_response": "",
            "action_items": ["Manual review required"],
            "warnings": [str(exc)],
            "confidence": 0.1,
        }
