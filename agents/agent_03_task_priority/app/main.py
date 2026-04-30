from fastapi import FastAPI, HTTPException
from shared.legal_agents.base_agent import build_router
from shared.legal_agents.logging_utils import configure_logging
from shared.legal_agents.settings import settings
from .processor import process
from shared.legal_agents.schemas import GenericAgentRequest
from .services.task_repository import list_pending_tasks, list_all_tasks, update_task
from .services.planner import build_daily_plan

from fastapi.middleware.cors import CORSMiddleware

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

configure_logging(settings.log_level)

app = FastAPI(title="Task & Priority Management Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(build_router("task_priority", "Task & Priority Management Agent", process))
BASE_DIR = Path(__file__).resolve().parent

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

@app.get("/health")
def health():
    return {"status": "ok", "agent": "task_priority"}

@app.post("/api/tasks/create")
def create_task(payload: dict):
    try:
        result = process(GenericAgentRequest(payload=payload))

        return {
            "status": "ok",
            "task": result.get("task"),
            "sheet_sync": result.get("sheet_sync"),
            "alert": result.get("alert"),
        }

    except Exception as exc:
        print("Task creation error:", exc)

        raise HTTPException(
            status_code=500,
            detail=f"Task creation failed: {str(exc)}"
        )

@app.get("/api/tasks")
def get_tasks():
    return {
        "status": "ok",
        "items": list_all_tasks(),
    }

@app.patch("/api/tasks/{task_id}")
def patch_task(task_id: int, payload: dict):
    update_task(task_id, payload)
    return {"status": "ok"}

@app.post("/api/daily-plan/run")
def daily_plan():
    tasks = list_pending_tasks()
    todays_meetings = []
    hours_available = 6.0

    plan = build_daily_plan(
        tasks=tasks,
        todays_meetings=todays_meetings,
        hours_available=hours_available,
    )

    return {
        "status": "ok",
        "plan": plan,
    }

@app.get("/api/overview")
def overview():
    tasks = list_all_tasks()

    return {
        "status": "ok",
        "metrics": {
            "pending_tasks": len([t for t in tasks if t.get("status") == "pending"]),
            "high_priority_tasks": len([t for t in tasks if (t.get("priority_score") or 0) >= 80]),
            "overdue_tasks": 0,
            "total_tasks": len(tasks),
        },
        "tasks": tasks,
    }

