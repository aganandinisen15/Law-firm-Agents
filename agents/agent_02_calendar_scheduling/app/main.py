from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal
import json
import os
import re
import sqlite3
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.services.google_clients import GoogleWorkspaceClients

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("SCHEDULING_DB_PATH", BASE_DIR.parent / "calendar_agent.db"))

app = FastAPI(title="Calendar & Scheduling Agent", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class ScheduleRequest(BaseModel):
    request_text: str = Field(..., description="Original scheduling email or request")
    source: str = "manual"
    auto_create_event: bool = True
    requester_email: str | None = None
    matter_id: str | None = None


class MeetingDetails(BaseModel):
    title: str
    attendees: list[dict[str, str]]
    proposed_times: list[str]
    duration_minutes: int
    location: str
    notes: str = ""


# ---------- DB ----------
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id TEXT NOT NULL,
            title TEXT NOT NULL,
            attendees_json TEXT NOT NULL,
            scheduled_time TEXT,
            duration INTEGER NOT NULL,
            matter_id TEXT,
            calendar_event_id TEXT,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            location TEXT,
            notes TEXT,
            source TEXT
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            due_date TEXT,
            status TEXT NOT NULL,
            source TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_text TEXT NOT NULL,
            details_json TEXT,
            result_json TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


@app.on_event("startup")
def startup() -> None:
    init_db()


# ---------- Helpers ----------
def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def parse_request_text(text: str) -> MeetingDetails:
    lower = text.lower()

    title = "Client Meeting"
    if "lease" in lower:
        title = "Lease Comments Meeting"
    elif "closing" in lower:
        title = "Closing Coordination Meeting"
    elif "discovery" in lower:
        title = "Discovery Strategy Call"
    elif "schedule:" in lower:
        first = text.splitlines()[0].replace("SCHEDULE:", "").strip()
        title = first or title

    attendees = []
    for email in sorted(set(EMAIL_RE.findall(text))):
        name = email.split("@")[0].replace(".", " ").title()
        attendees.append({"name": name, "email": email})

    duration = 60
    duration_match = re.search(r"(\d{2,3})\s*(minute|minutes|min)", lower)
    if duration_match:
        duration = int(duration_match.group(1))

    location = "video call" if any(x in lower for x in ["zoom", "meet", "video", "call"]) else "in-person"

    proposed_times: list[str] = []
    base = datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=1)
    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
    }
    for day, idx in weekdays.items():
        if day in lower:
            ahead = (idx - base.weekday()) % 7
            target = base + timedelta(days=ahead)
            hour = 10
            if "afternoon" in lower:
                hour = 14
            elif "morning" in lower:
                hour = 10
            proposed_times.append(target.replace(hour=hour).isoformat())

    explicit_times = re.findall(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", lower)
    if explicit_times and proposed_times:
        enriched = []
        for i, t in enumerate(proposed_times[: len(explicit_times)]):
            dt = datetime.fromisoformat(t)
            hh, mm, mer = explicit_times[i]
            hour = int(hh) % 12 + (12 if mer == "pm" else 0)
            minute = int(mm or 0)
            enriched.append(dt.replace(hour=hour, minute=minute).isoformat())
        proposed_times = enriched or proposed_times

    if not proposed_times:
        proposed_times = [
            base.replace(hour=10).isoformat(),
            base.replace(hour=14).isoformat(),
        ]

    notes = "Attorney prefers mornings for client meetings; avoid 12:00-13:30 lunch block."
    return MeetingDetails(
        title=title,
        attendees=attendees,
        proposed_times=proposed_times,
        duration_minutes=duration,
        location=location,
        notes=notes,
    )


def check_availability(clients: GoogleWorkspaceClients, proposed_times: list[str], duration: int) -> list[dict[str, Any]]:
    results = []
    for ts in proposed_times:
        start_dt = datetime.fromisoformat(ts)
        end_dt = start_dt + timedelta(minutes=duration)
        available = clients.is_time_available(start_dt, end_dt)
        results.append(
            {
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "available": available,
                "reason": "free" if available else "calendar conflict or buffer violation",
            }
        )
    return results


def generate_alternatives(base_time: datetime, unavailable: list[dict[str, Any]]) -> list[dict[str, str]]:
    slots = []
    day_start = base_time.replace(hour=9, minute=0)
    for offset_days in range(0, 5):
        day = day_start + timedelta(days=offset_days)
        if day.weekday() >= 5:
            continue
        for hour in [9, 10, 11, 14, 15, 16]:
            if 12 <= hour < 14:
                continue
            slot = day.replace(hour=hour)
            slots.append(slot)
    return [
        {"time": s.isoformat(), "reason": "Morning preference respected" if s.hour < 12 else "Same-week alternative"}
        for s in slots[:3]
    ]


def save_meeting(details: MeetingDetails, scheduled_time: str | None, status: str, source: str, matter_id: str | None, calendar_event_id: str | None) -> None:
    conn = get_db()
    conn.execute(
        """
        INSERT INTO meetings (
            meeting_id, title, attendees_json, scheduled_time, duration, matter_id,
            calendar_event_id, created_at, status, location, notes, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            details.title,
            json.dumps(details.attendees),
            scheduled_time,
            details.duration_minutes,
            matter_id,
            calendar_event_id,
            now_iso(),
            status,
            details.location,
            details.notes,
            source,
        ),
    )
    if scheduled_time:
        prep_due = (datetime.fromisoformat(scheduled_time) - timedelta(days=1)).date().isoformat()
        conn.execute(
            "INSERT INTO tasks (title, due_date, status, source, created_at) VALUES (?, ?, ?, ?, ?)",
            (f"Prepare for {details.title}", prep_due, "pending", "calendar_agent", now_iso()),
        )
    conn.commit()
    conn.close()


def save_run_log(request_text: str, details: dict[str, Any], result: dict[str, Any], status: str) -> None:
    conn = get_db()
    conn.execute(
        "INSERT INTO run_log (request_text, details_json, result_json, status, created_at) VALUES (?, ?, ?, ?, ?)",
        (request_text, json.dumps(details), json.dumps(result), status, now_iso()),
    )
    conn.commit()
    conn.close()


# ---------- Routes ----------
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "agent": "calendar_scheduling"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Any:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/overview")
def overview() -> dict[str, Any]:
    conn = get_db()
    meetings = [dict(r) for r in conn.execute("SELECT * FROM meetings ORDER BY id DESC LIMIT 8").fetchall()]
    tasks = [dict(r) for r in conn.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT 8").fetchall()]
    runs = [dict(r) for r in conn.execute("SELECT * FROM run_log ORDER BY id DESC LIMIT 8").fetchall()]
    metrics = {
        "meetings_total": conn.execute("SELECT COUNT(*) FROM meetings").fetchone()[0],
        "scheduled_total": conn.execute("SELECT COUNT(*) FROM meetings WHERE status='scheduled'").fetchone()[0],
        "conflict_total": conn.execute("SELECT COUNT(*) FROM meetings WHERE status='conflict'").fetchone()[0],
        "draft_total": conn.execute("SELECT COUNT(*) FROM meetings WHERE status='drafted_alternatives'").fetchone()[0],
    }
    conn.close()
    return {
        "metrics": metrics,
        "meetings": meetings,
        "tasks": tasks,
        "runs": runs,
        "google": GoogleWorkspaceClients.from_env().status(),
    }


@app.post("/run")
def run_agent(payload: ScheduleRequest) -> dict[str, Any]:
    details = parse_request_text(payload.request_text)
    clients = GoogleWorkspaceClients.from_env()
    availability = check_availability(clients, details.proposed_times, details.duration_minutes)
    available_slots = [a for a in availability if a["available"]]
    conflicts = [a for a in availability if not a["available"]]

    result: dict[str, Any] = {
        "details": details.model_dump(),
        "availability": availability,
        "status": "parsed",
        "calendar_event_id": None,
        "gmail_action": None,
        "alternatives": [],
    }

    if available_slots and payload.auto_create_event:
        chosen = available_slots[0]
        event_id = clients.create_calendar_event(
            title=details.title,
            start_iso=chosen["start"],
            end_iso=chosen["end"],
            attendees=[a["email"] for a in details.attendees if a.get("email")],
            location=details.location,
            notes=details.notes,
            add_video=(details.location == "video call"),
        )
        result["status"] = "scheduled"
        result["calendar_event_id"] = event_id
        result["scheduled_time"] = chosen["start"]
        save_meeting(details, chosen["start"], "scheduled", payload.source, payload.matter_id, event_id)
    elif conflicts:
        base = datetime.fromisoformat(details.proposed_times[0])
        alternatives = generate_alternatives(base, conflicts)
        result["status"] = "conflict"
        result["alternatives"] = alternatives
        draft_body = clients.create_gmail_draft(
            to=payload.requester_email or (details.attendees[0]["email"] if details.attendees else ""),
            subject=f"Re: {details.title}",
            body=(
                "Thank you for the scheduling request. The proposed times conflict with the attorney's calendar. "
                "Here are three alternative options:\n\n" +
                "\n".join([f"- {a['time']} ({a['reason']})" for a in alternatives]) +
                "\n\nPlease confirm which option works best.\n\nLegal Team"
            ),
        )
        result["gmail_action"] = draft_body
        save_meeting(details, None, "drafted_alternatives", payload.source, payload.matter_id, None)
    else:
        save_meeting(details, None, "manual_review", payload.source, payload.matter_id, None)
        result["status"] = "manual_review"

    save_run_log(payload.request_text, details.model_dump(), result, result["status"])
    return result
