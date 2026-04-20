from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import calendar
import json
import os
import re
import sqlite3
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .services.google_clients import GoogleWorkspaceClients

IST = timezone(timedelta(hours=5, minutes=30))

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("SCHEDULING_DB_PATH", BASE_DIR.parent / "calendar_agent.db"))
DEFAULT_TIMEZONE = os.getenv("CALENDAR_DEFAULT_TIMEZONE", "Asia/Kolkata")

app = FastAPI(title="Calendar & Scheduling Agent", version="2.1.0")
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
    flexible: bool = False


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
WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def next_weekday(base: datetime, weekday: int) -> datetime:
    ahead = (weekday - base.weekday()) % 7
    if ahead == 0:
        ahead = 7
    return base + timedelta(days=ahead)


def infer_hour_minute(text: str) -> tuple[int, int]:
    lower = text.lower()
    explicit = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", lower)
    if explicit:
        hh = int(explicit.group(1)) % 12
        mm = int(explicit.group(2) or 0)
        mer = explicit.group(3)
        hour = hh + (12 if mer == "pm" else 0)
        return hour, mm
    if "afternoon" in lower:
        return 14, 0
    if "morning" in lower:
        return 10, 0
    return 10, 0


def resolve_preferred_datetime(text: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now().replace(second=0, microsecond=0)
    text = text.strip().lower()

    try:
        return datetime.fromisoformat(text)
    except Exception:
        pass

    hour, minute = infer_hour_minute(text)

    # full month + day e.g. april 18
    month_match = re.search(r"(" + "|".join(MONTHS.keys()) + r")", text)
    day_match = re.search(r"(\d{1,2})(st|nd|rd|th)?", text)
    if month_match and day_match:
        month = MONTHS[month_match.group(1)]
        day = int(day_match.group(1))
        year = now.year
        candidate = datetime(year, month, min(day, calendar.monthrange(year, month)[1]), hour, minute)
        if candidate < now:
            candidate = datetime(year + 1, month, min(day, calendar.monthrange(year + 1, month)[1]), hour, minute)
        return candidate

    # weekday references
    for label, idx in WEEKDAYS.items():
        if label in text:
            candidate = next_weekday(now, idx).replace(hour=hour, minute=minute)
            return candidate

    # ordinal day like 18th
    if day_match:
        day = int(day_match.group(1))
        year = now.year
        month = now.month
        last_day = calendar.monthrange(year, month)[1]
        candidate = datetime(year, month, min(day, last_day), hour, minute)
        if candidate < now:
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
            last_day = calendar.monthrange(year, month)[1]
            candidate = datetime(year, month, min(day, last_day), hour, minute)
        return candidate

    # fallback: next business day at preferred/default time
    candidate = (now + timedelta(days=1)).replace(hour=hour, minute=minute)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate

def ensure_preferred_time_first(request_text: str, proposed_times: list[str]) -> list[str]:
    try:
        preferred = parse_preferred_datetime(request_text).isoformat()
        cleaned = [t for t in proposed_times if t != preferred]
        return [preferred] + cleaned
    except Exception:
        return proposed_times

def parse_preferred_datetime(request_text: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now(IST)
    text = request_text.lower().strip()

    # Match patterns like "25th april 2026 at 3pm"
    match = re.search(
        r'(\d{1,2})(st|nd|rd|th)?\s+'
        r'(january|february|march|april|may|june|july|august|september|october|november|december)'
        r'\s+(\d{4})'
        r'(?:\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?)?',
        text,
    )

    if match:
        day = int(match.group(1))
        month_name = match.group(3)
        year = int(match.group(4))
        hour = int(match.group(5)) if match.group(5) else 10
        minute = int(match.group(6)) if match.group(6) else 0
        ampm = match.group(7)

        month = list(calendar.month_name).index(month_name.capitalize())

        if ampm:
            if ampm.lower() == "pm" and hour != 12:
                hour += 12
            elif ampm.lower() == "am" and hour == 12:
                hour = 0

        return datetime(year, month, day, hour, minute, 0, tzinfo=IST)

    # Match patterns like "25th at 3pm" or "25 april"
    match = re.search(
        r'(\d{1,2})(st|nd|rd|th)?'
        r'(?:\s+'
        r'(january|february|march|april|may|june|july|august|september|october|november|december))?'
        r'(?:\s+(\d{4}))?'
        r'(?:\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?)?',
        text,
    )

    if match:
        day = int(match.group(1))
        month_name = match.group(3)
        year = int(match.group(4)) if match.group(4) else now.year
        hour = int(match.group(5)) if match.group(5) else 10
        minute = int(match.group(6)) if match.group(6) else 0
        ampm = match.group(7)

        month = list(calendar.month_name).index(month_name.capitalize()) if month_name else now.month

        if ampm:
            if ampm.lower() == "pm" and hour != 12:
                hour += 12
            elif ampm.lower() == "am" and hour == 12:
                hour = 0

        candidate = datetime(year, month, day, hour, minute, 0, tzinfo=IST)

        if candidate < now:
            # If inferred date is in the past, move to next month only when month/year not explicitly given
            if not month_name and not match.group(4):
                if month == 12:
                    candidate = candidate.replace(year=year + 1, month=1)
                else:
                    last_day = calendar.monthrange(year, month + 1)[1]
                    candidate = candidate.replace(month=month + 1, day=min(day, last_day))

        return candidate

    raise ValueError(f"Could not parse preferred datetime from request: {request_text}")


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
    flexible = any(x in lower for x in ["or", "either", "available", "next week", "works best"])

    proposed_times: list[str] = []
    now = datetime.now().replace(second=0, microsecond=0)

    # Extract explicit options like Tuesday or Wednesday, next Tuesday, April 18, 18th
    if any(day in lower for day in WEEKDAYS):
        for label in WEEKDAYS:
            if label in lower:
                proposed_times.append(resolve_preferred_datetime(label + " " + lower, now).isoformat())
    else:
        # month/day or ordinal day or fallback
        proposed_times.append(resolve_preferred_datetime(lower, now).isoformat())

    # add a second option only if request seems flexible or only one option provided
    if len(proposed_times) == 1 and flexible:
        alt = datetime.fromisoformat(proposed_times[0]) + timedelta(hours=4)
        if 12 <= alt.hour < 14:
            alt = alt.replace(hour=14, minute=0)
        proposed_times.append(alt.isoformat())

    # de-duplicate preserve order
    seen = set()
    deduped = []
    for p in proposed_times:
        if p not in seen:
            deduped.append(p)
            seen.add(p)
    proposed_times = deduped[:3]

    notes = "Attorney prefers mornings for client meetings; avoid 12:00-13:30 lunch block; preserve requester preferred date first."
    return MeetingDetails(
        title=title,
        attendees=attendees,
        proposed_times=proposed_times,
        duration_minutes=duration,
        location=location,
        notes=notes,
        flexible=flexible,
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

import re

def contains_scheduling_request(subject: str, body: str) -> bool:
    text = f"{subject}\n{body}".lower()

    patterns = [
        r"\bschedule\b",
        r"\bmeeting\b",
        r"\bcall\b",
        r"\bavailability\b",
        r"\bavailable\b",
        r"\bbook\b",
        r"\bnext tuesday\b",
        r"\bnext wednesday\b",
        r"\bnext week\b",
        r"\bat \d{1,2}(:\d{2})?\s?(am|pm)\b",
        r"\bon \d{1,2}(st|nd|rd|th)?\b",
        r"^schedule:",
    ]

    return any(re.search(pattern, text) for pattern in patterns)

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
        "scheduled_total": conn.execute("SELECT COUNT(*) FROM meetings WHERE status LIKE 'scheduled%'").fetchone()[0],
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

    # Use the actual request text from payload, not an undefined request object
    details.proposed_times = ensure_preferred_time_first(
        request_text=payload.request_text,
        proposed_times=details.proposed_times,
    )

    availability = check_availability(clients, details.proposed_times, details.duration_minutes)
    available_slots = [a for a in availability if a["available"]]
    conflicts = [a for a in availability if not a["available"]]

    result: dict[str, Any] = {
        "details": details.model_dump(),
        "preferred_time": details.proposed_times[0] if details.proposed_times else None,
        "availability": availability,
        "status": "parsed",
        "calendar_event_id": None,
        "calendar_event_link": None,
        "gmail_action": None,
        "alternatives": [],
        "google_mode": clients.status(),
        "scheduled_time": None,
    }

    if available_slots and payload.auto_create_event:
        # First available slot should now be the user's preferred slot if free
        chosen = available_slots[0]

        event_info = clients.create_calendar_event(
            title=details.title,
            start_iso=chosen["start"],
            end_iso=chosen["end"],
            attendees=[a["email"] for a in details.attendees if a.get("email")],
            location=details.location,
            notes=details.notes,
            add_video=(details.location == "video call"),
        )

        # Match the keys returned by create_calendar_event()
        result["status"] = "scheduled_google" if clients.enabled else "scheduled_local"
        result["calendar_event_id"] = event_info.get("event_id")
        result["calendar_event_link"] = event_info.get("event_link")
        result["scheduled_time"] = chosen["start"]

        save_meeting(
            details,
            chosen["start"],
            result["status"],
            payload.source,
            payload.matter_id,
            event_info.get("event_id"),
        )

    elif conflicts:
        base = datetime.fromisoformat(details.proposed_times[0])
        alternatives = generate_alternatives(base, conflicts)

        result["status"] = "conflict"
        result["alternatives"] = alternatives

        draft_body = clients.create_gmail_draft(
            to=payload.requester_email or (details.attendees[0]["email"] if details.attendees else ""),
            subject=f"Re: {details.title}",
            body=(
                "Thank you for the scheduling request. "
                "The preferred time conflicts with the attorney's calendar.\n\n"
                "Here are three alternative options:\n"
                + "\n".join([f"- {a['time']} ({a['reason']})" for a in alternatives])
                + "\n\nPlease confirm which option works best.\n\nLegal Team"
            ),
        )

        result["gmail_action"] = draft_body
        save_meeting(details, None, "drafted_alternatives", payload.source, payload.matter_id, None)

    else:
        save_meeting(details, None, "manual_review", payload.source, payload.matter_id, None)
        result["status"] = "manual_review"

    save_run_log(payload.request_text, details.model_dump(), result, result["status"])
    return result
