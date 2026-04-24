from fastapi import FastAPI, HTTPException
from shared.legal_agents.base_agent import build_router
from shared.legal_agents.logging_utils import configure_logging
from shared.legal_agents.settings import settings
from .processor import process
from shared.legal_agents.schemas import GenericAgentRequest
from .services.task_repository import list_pending_tasks, update_task
from .services.planner import build_daily_plan

configure_logging(settings.log_level)

app = FastAPI(title="Task & Priority Management Agent", version="0.1.0")
app.include_router(build_router("task_priority", "Task & Priority Management Agent", process))

@app.get("/health")
def health():
    return {"status": "ok", "agent": "task_priority"}

@app.post("/api/tasks/create")
def create_task(payload: dict):
    try:
        return process(GenericAgentRequest(payload=payload))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/api/tasks")
def get_tasks():
    return {
        "status": "ok",
        "items": list_pending_tasks(),
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
    plan = build_daily_plan(tasks, todays_meetings, hours_available)
    return {"status": "ok", "plan": plan}

@app.get("/api/overview")
def overview():
    tasks = list_pending_tasks()
    overdue_count = 0
    high_priority_count = sum(1 for t in tasks if (t.get("priority_score") or 0) > 80)

    return {
        "status": "ok",
        "metrics": {
            "pending_tasks": len(tasks),
            "high_priority_tasks": high_priority_count,
            "overdue_tasks": overdue_count,
        },
        "tasks": tasks[:10],
    }

