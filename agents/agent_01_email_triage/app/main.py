from __future__ import annotations

from asyncio import tasks
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from shared.legal_agents.adapters import GoogleWorkspaceAdapter
from shared.legal_agents.base_agent import build_router
from shared.legal_agents.db import engine
from shared.legal_agents.logging_utils import configure_logging
from shared.legal_agents.schemas import GenericAgentRequest
from shared.legal_agents.settings import settings
from .processor import process

import re
import requests

import os

TASK_AGENT_URL = os.getenv(
    "TASK_AGENT_URL",
    "http://localhost:8013/api/tasks/create"
)
def create_task_from_email(payload: dict) -> dict:
    try:
        response = requests.post(TASK_AGENT_URL, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print("Task Agent call failed:", e)
        return {
            "status": "task_agent_error",
            "error": str(e),
            "payload": payload,
        }

CALENDAR_AGENT_URL = os.getenv(
    "CALENDAR_AGENT_URL",
    "http://localhost:8012/run"
)

configure_logging(settings.log_level)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))
google_adapter = GoogleWorkspaceAdapter()

app = FastAPI(
    title="LexFlow Email Triage Admin",
    version="4.0.0",
    description="Admin console for Gmail-driven legal email triage, routing, and response drafting.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(build_router("email_triage", "Email Triage Agent", process))


class GmailWatcher:
    def __init__(self, adapter: GoogleWorkspaceAdapter):
        self.adapter = adapter
        self.running = False
        self.poll_seconds = 30
        self.query = settings.gmail_default_query
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.last_checked_at: Optional[str] = None
        self.last_processed_at: Optional[str] = None
        self.last_error: Optional[str] = None
        self.last_message_id: Optional[str] = None
        self.processed_session_count = 0

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "running": self.running,
                "poll_seconds": self.poll_seconds,
                "query": self.query,
                "last_checked_at": self.last_checked_at,
                "last_processed_at": self.last_processed_at,
                "last_error": self.last_error,
                "last_message_id": self.last_message_id,
                "processed_session_count": self.processed_session_count,
            }

    def configure(self, poll_seconds: Optional[int] = None, query: Optional[str] = None) -> None:
        with self.lock:
            if poll_seconds:
                self.poll_seconds = max(10, min(int(poll_seconds), 300))
            if query is not None:
                self.query = query.strip() or settings.gmail_default_query

    def start(self, poll_seconds: Optional[int] = None, query: Optional[str] = None) -> Dict[str, Any]:
        self.configure(poll_seconds, query)
        with self.lock:
            if self.running:
                return self.snapshot()
            self.running = True
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._loop, daemon=True, name="gmail-watcher")
            self.thread.start()
            return self.snapshot()

    def stop(self) -> Dict[str, Any]:
        with self.lock:
            self.running = False
            self.stop_event.set()
        return self.snapshot()

    def run_once(self) -> Dict[str, Any]:
        try:
            payload = _find_latest_unprocessed_message(max_results=10, query=self.query)
            checked_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            with self.lock:
                self.last_checked_at = checked_at
            if not payload:
                return {"processed": False, "message": None, "checked_at": checked_at}
            workflow = _workflow_result(payload)
            with self.lock:
                self.last_processed_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                self.last_message_id = payload.get("gmail_message_id") or payload.get("email_id")
                self.processed_session_count += 1
                self.last_error = None
            return {"processed": True, "message": payload, "workflow": workflow, "checked_at": checked_at}
        except Exception as exc:  # pragma: no cover
            with self.lock:
                self.last_error = str(exc)
                self.last_checked_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            raise

    def _loop(self) -> None:
        while not self.stop_event.wait(self.poll_seconds):
            if not self.running:
                break
            try:
                self.run_once()
            except Exception:
                pass


watcher = GmailWatcher(google_adapter)


def _looks_like_scheduling(text_value: str) -> bool:
    lower = (text_value or "").lower()
    keywords = ["schedule", "meeting", "call", "availability", "calendar", "zoom"]
    return any(word in lower for word in keywords)


def _dashboard_metrics() -> Dict[str, Any]:
    with engine.begin() as conn:
        email_metrics = conn.execute(
            text(
                """
                SELECT
                  COUNT(*) AS total_processed,
                  COUNT(*) FILTER (WHERE urgency_score >= :urgent_threshold) AS urgent_count,
                  COUNT(*) FILTER (WHERE draft_created IS TRUE) AS drafts_created,
                  COUNT(*) FILTER (WHERE category = 'COURT') AS court_count,
                  COUNT(*) FILTER (WHERE category = 'NEEDS_MANUAL_REVIEW') AS manual_review_count
                FROM email_log
                """
            ),
            {"urgent_threshold": settings.email_triage_urgent_threshold},
        ).mappings().one()
        task_metrics = conn.execute(
            text(
                """
                SELECT COUNT(*) AS total_tasks,
                       COUNT(*) FILTER (WHERE status = 'pending') AS pending_tasks,
                       COALESCE(MAX(priority_score), 0) AS top_priority
                FROM tasks
                """
            )
        ).mappings().one()
        meeting_metrics = conn.execute(
            text(
                """
                SELECT COUNT(*) AS total_meetings,
                       COUNT(*) FILTER (WHERE status = 'tentative') AS tentative_meetings,
                       COUNT(*) FILTER (WHERE scheduled_time::date >= CURRENT_DATE) AS upcoming_meetings
                FROM meetings
                """
            )
        ).mappings().one()
        deadline_metrics = conn.execute(
            text(
                """
                SELECT COUNT(*) AS total_deadlines,
                       COUNT(*) FILTER (WHERE status = 'upcoming') AS upcoming_deadlines
                FROM deadlines
                """
            )
        ).mappings().one()
    return {
        "emails": dict(email_metrics),
        "tasks": dict(task_metrics),
        "meetings": dict(meeting_metrics),
        "deadlines": dict(deadline_metrics),
    }


def _normalize_email_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "email_id": payload.get("email_id") or payload.get("gmail_message_id"),
        "gmail_message_id": payload.get("gmail_message_id") or payload.get("email_id"),
        "thread_id": payload.get("thread_id"),
        "from": payload.get("from") or payload.get("sender") or "",
        "subject": payload.get("subject") or "",
        "body": payload.get("body") or payload.get("snippet") or "",
        "attachments": payload.get("attachments") or [],
        "metadata": payload.get("metadata") or {},
    }


def _find_latest_unprocessed_message(max_results: int = 10, query: str | None = None) -> Dict[str, Any] | None:
    inbox = google_adapter.list_inbox_messages(max_results=max_results, query=query or "")
    items = inbox.get("items", [])
    if not items:
        return None

    message_ids = [item.get("gmail_message_id") for item in items if item.get("gmail_message_id")]
    processed_ids: set[str] = set()
    if message_ids:
        with engine.begin() as conn:
            rows = conn.execute(
                text("SELECT email_id FROM email_log WHERE email_id = ANY(:ids)"),
                {"ids": message_ids},
            ).fetchall()
        processed_ids = {row[0] for row in rows}

    for item in items:
        message_id = item.get("gmail_message_id")
        if message_id and message_id not in processed_ids:
            return item
    return None


def _triage_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    email_payload = _normalize_email_payload(payload)
    result = process(GenericAgentRequest(payload=email_payload, metadata=payload.get("metadata") or {}))
    return {
        "status": "ok",
        "summary": result.get("summary", "Email processed."),
        "data": result,
    }


def _create_deadline_if_needed(payload: Dict[str, Any], triage_response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    deadline = triage_response.get("deadline")
    if not deadline:
        return None
    if triage_response.get("category") != "COURT":
        return None
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO deadlines (deadline_type, deadline_date, description, source, reminder_schedule, status)
                    VALUES (:deadline_type, :deadline_date, :description, :source, CAST(:reminder_schedule AS JSONB), :status)
                    RETURNING deadline_id
                    """
                ),
                {
                    "deadline_type": "court",
                    "deadline_date": deadline,
                    "description": f"Court communication: {payload.get('subject', 'Untitled')}",
                    "reminder_schedule": '{"default": [14, 7, 3, 1]}',
                    "source": "email_triage",
                    "status": "upcoming",
                },
            ).mappings().one()
        return {"deadline_id": row["deadline_id"], "deadline": deadline}
    except Exception:
        return None


def contains_scheduling_request(subject: str, body: str) -> bool:
    text = f"{subject}\n{body}".lower().strip()

    patterns = [
        r"^schedule:",
        r"\bschedule\b",
        r"\bmeeting\b",
        r"\bcall\b",
        r"\bavailability\b",
        r"\bavailable\b",
        r"\bbook\b",
        r"\bset up a meeting\b",
        r"\bcan we meet\b",
        r"\bnext monday\b",
        r"\bnext tuesday\b",
        r"\bnext wednesday\b",
        r"\bnext thursday\b",
        r"\bnext friday\b",
        r"\bnext week\b",
        r"\bon \d{1,2}(st|nd|rd|th)?\b",
        r"\bat \d{1,2}(:\d{2})?\s?(am|pm)\b",
    ]

    return any(re.search(pattern, text) for pattern in patterns)


def should_trigger_calendar(category: str, subject: str, body: str) -> bool:
    if subject.strip().upper().startswith("SCHEDULE:"):
        return True

    allowed_categories = {
        "URGENT_CLIENT",
        "CLIENT_ROUTINE",
        "ADMIN",
        "BUSINESS_DEV",
    }

    if category not in allowed_categories:
        return False

    return contains_scheduling_request(subject, body)


def call_calendar_agent(payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        CALENDAR_AGENT_URL,
        json=payload,
        timeout=45,
    )
    response.raise_for_status()
    return response.json()


def _workflow_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    triage_response = _triage_result(payload)["data"]

    subject = payload.get("subject", "") or ""
    body = payload.get("body", "") or ""
    sender = payload.get("from") or payload.get("sender") or ""

    # ---------------- TASK CREATION ----------------
    tasks: List[Dict[str, Any]] = []

    for idx, action_item in enumerate(triage_response.get("action_items", [])[:3], start=1):
        tags = ["email", triage_response.get("category", "client_routine").lower()]

        if triage_response.get("deadline"):
            tags.append("deadline")

        if triage_response.get("urgency_score", 0) >= settings.email_triage_urgent_threshold:
            tags.append("urgent")

        if triage_response.get("category") == "COURT":
            tags.append("court")

        task_payload = {
            "title": action_item if len(action_item) > 6 else f"Task {idx}: {subject or 'Email follow-up'}",
            "description": triage_response.get("key_points") or f"{subject}\n\n{body}",
            "due_date": triage_response.get("deadline"),
            "source": "email_triage_agent",
            "tags": tags,
        }

        task_result = create_task_from_email(task_payload)
        tasks.append(task_result)

    # ---------------- CALENDAR TRIGGER ----------------
    calendar_result = None

    calendar_triggered = should_trigger_calendar(
        triage_response.get("category", ""),
        subject,
        body,
    )

    if calendar_triggered:
        try:
            calendar_payload = {
                "request_text": f"Subject: {subject}\n\nBody:\n{body}",
                "requester_email": sender,
                "matter_id": None,
                "source": "email_triage_agent",
                "auto_create_event": True,
            }

            calendar_result = call_calendar_agent(calendar_payload)

        except Exception as exc:
            calendar_result = {
                "status": "calendar_error",
                "error": str(exc),
            }

    # ---------------- DEADLINE ----------------
    deadline_result = _create_deadline_if_needed(payload, triage_response)

    # ---------------- FINAL RESPONSE ----------------
    return {
        "status": "ok",
        "summary": "Workflow processed with triage, tasks, deadlines, and scheduling.",
        "triage": triage_response,
        "tasks": tasks,
        "calendar_triggered": calendar_triggered,
        "calendar": calendar_result,
        "deadline": deadline_result,
        "routing": {
            "task_count": len(tasks),
            "calendar_triggered": calendar_triggered,
            "deadline_triggered": deadline_result is not None,
            "requires_response": triage_response.get("requires_response", False),
        },
    }


def _recent_processed(limit: int = 12) -> List[Dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT sender, subject, category, urgency_score, requires_response, draft_created, processed_at
                FROM email_log
                ORDER BY processed_at DESC NULLS LAST
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
    return [dict(row) for row in rows]


def _recent_errors(limit: int = 8) -> List[Dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT agent_slug, error_message, correlation_id, created_at
                FROM error_log
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
    return [dict(row) for row in rows]


def _recent_tasks(limit: int = 8) -> List[Dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT title, priority_score, status, due_date, created_at
                FROM tasks
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
    return [dict(row) for row in rows]


@app.get("/", response_class=HTMLResponse)
def frontend(request: Request):
    return TEMPLATES.TemplateResponse(
        "index.html",
        {
            "request": request,
            "page_title": "LexFlow Email Triage Admin",
            "app_env": settings.app_env,
            "use_claude": settings.email_triage_use_claude,
            "gmail_configured": google_adapter.is_gmail_configured(),
            "gmail_query": settings.gmail_default_query,
            "urgent_threshold": settings.email_triage_urgent_threshold,
        },
    )


@app.get("/api/admin/overview")
def admin_overview():
    return {
        "status": "ok",
        "metrics": _dashboard_metrics(),
        "watcher": watcher.snapshot(),
        "gmail": {
            "configured": google_adapter.is_gmail_configured(),
            "mailbox_user": settings.gmail_mailbox_user,
            "default_query": settings.gmail_default_query,
        },
        "recent_processed": _recent_processed(),
        "recent_errors": _recent_errors(),
        "recent_tasks": _recent_tasks(),
    }


@app.post("/api/admin/automation/start")
def start_automation(payload: Dict[str, Any]):
    return {"status": "ok", "watcher": watcher.start(payload.get("poll_seconds"), payload.get("query"))}


@app.post("/api/admin/automation/stop")
def stop_automation():
    return {"status": "ok", "watcher": watcher.stop()}


@app.post("/api/admin/automation/run-once")
def run_automation_once(payload: Dict[str, Any] | None = None):
    if payload:
        watcher.configure(payload.get("poll_seconds"), payload.get("query"))
    try:
        return {"status": "ok", **watcher.run_once()}
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Could not process latest Gmail message: {exc}")


@app.post("/api/admin/manual/triage")
def manual_triage(payload: Dict[str, Any]):
    return _triage_result(payload)


@app.post("/api/admin/manual/workflow")
def manual_workflow(payload: Dict[str, Any]):
    return _workflow_result(payload)


@app.get("/api/history")
def history(limit: int = 20):
    safe_limit = min(max(limit, 1), 100)
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT email_id, sender, subject, category, urgency_score,
                           requires_response, draft_created, action_items, processed_at
                    FROM email_log
                    ORDER BY processed_at DESC NULLS LAST
                    LIMIT :limit
                    """
                ),
                {"limit": safe_limit},
            ).mappings().all()
        return {"status": "ok", "items": [dict(row) for row in rows]}
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Could not fetch history: {exc}")


@app.get("/api/tasks")
def task_history(limit: int = 10):
    safe_limit = min(max(limit, 1), 50)
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT task_id, title, due_date, priority_score, status, tags, created_at
                    FROM tasks
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": safe_limit},
            ).mappings().all()
        return {"status": "ok", "items": [dict(row) for row in rows]}
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Could not fetch tasks: {exc}")


@app.get("/api/meetings")
def meeting_history(limit: int = 10):
    safe_limit = min(max(limit, 1), 50)
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT meeting_id, title, scheduled_time, duration, calendar_event_id, status, created_at
                    FROM meetings
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": safe_limit},
            ).mappings().all()
        return {"status": "ok", "items": [dict(row) for row in rows]}
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Could not fetch meetings: {exc}")


@app.get("/api/metrics")
def metrics():
    try:
        return {"status": "ok", "metrics": _dashboard_metrics()}
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Could not fetch metrics: {exc}")
