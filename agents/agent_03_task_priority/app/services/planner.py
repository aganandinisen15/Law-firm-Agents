from __future__ import annotations

from datetime import date


def estimate_task_hours(task: dict) -> float:
    tags = {t.lower() for t in (task.get("tags") or [])}

    if "court" in tags or "discovery" in tags:
        return 2.0
    if "meeting_prep" in tags:
        return 1.0
    if "client_request" in tags:
        return 1.0
    return 1.0


def build_daily_plan(tasks: list[dict], todays_meetings: list[dict], hours_available: float) -> dict:
    overdue_tasks = []
    deferred_tasks = []
    top_5_tasks = []
    alerts = []

    used_hours = 0.0
    today = date.today()

    for task in tasks:
        due_date = task.get("due_date")
        if due_date and hasattr(due_date, "toordinal"):
            if due_date < today:
                overdue_tasks.append(task)

    sorted_tasks = sorted(
        tasks,
        key=lambda t: (
            -(t.get("manual_priority_override") or t.get("priority_score") or 0),
            t.get("due_date") or today,
        ),
    )

    for task in sorted_tasks:
        estimated_hours = estimate_task_hours(task)
        if len(top_5_tasks) < 5 and used_hours + estimated_hours <= hours_available:
            top_5_tasks.append({
                "task_id": task["task_id"],
                "title": task["title"],
                "estimated_time": f"{estimated_hours:.0f} hour" if estimated_hours == 1 else f"{estimated_hours:.0f} hours",
                "why_priority": task.get("priority_reasoning") or "High priority task",
            })
            used_hours += estimated_hours
        else:
            deferred_tasks.append(task)

    for task in overdue_tasks:
        alerts.append(f"Task {task['title']} is overdue.")

    return {
        "top_5_tasks": top_5_tasks,
        "deferred_tasks": deferred_tasks,
        "overdue_tasks": overdue_tasks,
        "alerts": alerts,
        "todays_meetings": todays_meetings,
        "hours_available": hours_available,
    }