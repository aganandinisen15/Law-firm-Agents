from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from shared.legal_agents.logging_utils import configure_logging
from shared.legal_agents.schemas import GenericAgentRequest
from shared.legal_agents.settings import settings

# Reuse existing agent modules, but call them in-process instead of HTTP.
from agents.agent_01_email_triage.app import main as email_agent
from agents.agent_02_calendar_scheduling.app import main as calendar_agent
from agents.agent_03_task_priority.app import main as task_agent
from agents.agent_04_document_organization.app import processor as document_processor

configure_logging(settings.log_level)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(
    title="Unified Legal Operations Agent",
    version="1.0.0",
    description="Single-agent version combining Email Triage, Calendar Scheduling, Task Priority, and Document Organization.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Keep original workflow so we can add document processing around it.
_original_email_workflow = email_agent._workflow_result


def _create_task_internal(payload: dict[str, Any]) -> dict[str, Any]:
    """Task creation without service-to-service HTTP."""
    return task_agent.create_task(payload)


def _calendar_internal(payload: dict[str, Any]) -> dict[str, Any]:
    """Calendar scheduling without service-to-service HTTP."""
    req = calendar_agent.ScheduleRequest(**payload)
    return calendar_agent.run_agent(req)


def _document_internal(payload: dict[str, Any]) -> dict[str, Any]:
    """Document organization without service-to-service HTTP."""
    normalized = {
        "filename": payload.get("filename") or payload.get("original_filename") or "email_attachment.pdf",
        "original_filename": payload.get("original_filename") or payload.get("filename") or "email_attachment.pdf",
        "file_type": payload.get("file_type") or payload.get("mime_type") or "pdf",
        "extracted_text": payload.get("extracted_text") or payload.get("body") or "",
        "document_type": payload.get("document_type") or "misc",
        "client_name": payload.get("client_name") or "Unknown Client",
        "matter_name": payload.get("matter_name") or payload.get("email_subject") or "Unknown Matter",
        "document_date": payload.get("document_date") or datetime.utcnow().date().isoformat(),
        "description": payload.get("description") or payload.get("suggested_description") or "FiledDocument",
        "source": payload.get("source") or "manual_upload",
    }
    result = document_processor.process(GenericAgentRequest(payload=normalized))
    return {"status": "ok", **result}


def _email_attachment_to_document_payload(attachment: dict[str, Any], email_payload: dict[str, Any], triage: dict[str, Any]) -> dict[str, Any]:
    return {
        "original_filename": attachment.get("filename") or "email_attachment.pdf",
        "file_type": attachment.get("mime_type") or attachment.get("file_type") or "pdf",
        "extracted_text": attachment.get("extracted_text") or email_payload.get("body") or "",
        "source": "email_attachment",
        "email_subject": email_payload.get("subject"),
        "sender": email_payload.get("from") or email_payload.get("sender"),
        "triage_category": triage.get("category"),
        "urgency_score": triage.get("urgency_score"),
        "document_type": attachment.get("document_type") or "misc",
        "description": attachment.get("description") or email_payload.get("subject") or "EmailAttachment",
    }


def _unified_email_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Email workflow + task/calendar/document integration, all in one process."""
    result = _original_email_workflow(payload)
    triage = result.get("triage") or {}

    documents: List[Dict[str, Any]] = []
    for attachment in payload.get("attachments", []) or []:
        try:
            doc_payload = _email_attachment_to_document_payload(attachment, payload, triage)
            documents.append(_document_internal(doc_payload))
        except Exception as exc:
            documents.append({
                "status": "document_error",
                "error": str(exc),
                "attachment": attachment,
            })

    result["documents"] = documents
    result["summary"] = "Unified workflow processed email, documents, tasks, deadlines, and scheduling."
    result.setdefault("routing", {})["document_count"] = len(documents)
    return result


# Monkey-patch Agent 1 dependencies so watcher/manual workflow use internal calls.
email_agent.create_task_from_email = _create_task_internal
email_agent.call_calendar_agent = _calendar_internal
email_agent._workflow_result = _unified_email_workflow


@app.on_event("startup")
def startup() -> None:
    # Calendar uses its own sqlite DB; initialize it when unified app starts.
    try:
        calendar_agent.init_db()
    except Exception as exc:
        print("Calendar DB init warning:", exc)


@app.get("/", response_class=HTMLResponse)
def frontend(request: Request):
    return TEMPLATES.TemplateResponse(
        "index.html",
        {
            "request": request,
            "page_title": "Unified Legal Operations Agent",
            "app_env": settings.app_env,
            "use_claude": settings.email_triage_use_claude,
            "gmail_configured": email_agent.google_adapter.is_gmail_configured(),
            "gmail_query": settings.gmail_default_query,
            "urgent_threshold": settings.email_triage_urgent_threshold,
        },
    )


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "agent": "unified_legal_operations",
        "includes": ["email_triage", "calendar_scheduling", "task_priority", "document_organization"],
    }


@app.get("/api/overview")
def unified_overview() -> dict[str, Any]:
    return {
        "status": "ok",
        "email": email_agent.admin_overview(),
        "calendar": calendar_agent.overview(),
        "tasks": task_agent.overview(),
        "documents": document_overview(),
    }


# ---------------- Email routes ----------------
@app.get("/api/admin/overview")
def admin_overview():
    return email_agent.admin_overview()


@app.post("/api/admin/automation/start")
def start_automation(payload: Dict[str, Any]):
    return email_agent.start_automation(payload)


@app.post("/api/admin/automation/stop")
def stop_automation():
    return email_agent.stop_automation()


@app.post("/api/admin/automation/run-once")
def run_automation_once(payload: Optional[Dict[str, Any]] = None):
    return email_agent.run_automation_once(payload)


@app.post("/api/admin/manual/triage")
def manual_triage(payload: Dict[str, Any]):
    return email_agent.manual_triage(payload)


@app.post("/api/admin/manual/workflow")
def manual_workflow(payload: Dict[str, Any]):
    return _unified_email_workflow(payload)


@app.get("/api/history")
def history(limit: int = 20):
    return email_agent.history(limit)


# ---------------- Calendar routes ----------------
@app.get("/api/calendar/overview")
def calendar_overview_alias():
    return calendar_agent.overview()


@app.get("/api/meetings")
def meeting_history(limit: int = 10):
    return email_agent.meeting_history(limit)


@app.post("/run")
def calendar_run_compat(payload: calendar_agent.ScheduleRequest):
    return calendar_agent.run_agent(payload)


@app.post("/api/calendar/schedule")
def calendar_schedule(payload: calendar_agent.ScheduleRequest):
    return calendar_agent.run_agent(payload)


# Existing frontend expects /api/overview for calendar when API.calendar points to same host.
# It is handled by unified_overview, so app.js uses /api/calendar/overview for calendar.

# ---------------- Task routes ----------------
@app.post("/api/tasks/create")
def create_task(payload: dict):
    return task_agent.create_task(payload)


@app.get("/api/tasks")
def get_tasks():
    return task_agent.get_tasks()


@app.patch("/api/tasks/{task_id}")
def patch_task(task_id: int, payload: dict):
    return task_agent.patch_task(task_id, payload)


@app.post("/api/daily-plan/run")
def daily_plan():
    return task_agent.daily_plan()


@app.get("/api/tasks/overview")
def task_overview_alias():
    return task_agent.overview()


# ---------------- Document routes ----------------
_DOCUMENTS: list[dict[str, Any]] = []


@app.post("/api/documents/file")
def file_document(payload: Dict[str, Any]):
    try:
        result = _document_internal(payload)
        record = {
            "id": len(_DOCUMENTS) + 1,
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "original_filename": payload.get("original_filename") or payload.get("filename"),
            **result,
        }
        _DOCUMENTS.insert(0, record)
        return record
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Document organization failed: {exc}")


@app.post("/api/documents/from-email")
def file_document_from_email(payload: Dict[str, Any]):
    payload = {**payload, "source": "email_attachment"}
    return file_document(payload)


@app.get("/api/documents/overview")
def document_overview():
    return {
        "status": "ok",
        "metrics": {
            "total_documents": len(_DOCUMENTS),
            "manual_review": len([d for d in _DOCUMENTS if d.get("warnings")]),
        },
        "documents": _DOCUMENTS[:20],
    }
