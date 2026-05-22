from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List

from sqlalchemy import text

from shared.legal_agents.db import engine
from shared.legal_agents.db_utils import log_audit, log_error
from shared.legal_agents.schemas import GenericAgentRequest
from .services.priority_engine import calculate_priority_score
from .services.task_repository import get_matter, insert_task
from .services.google_sheets import sync_task_to_sheet
from .services.notifications import maybe_send_high_priority_alert

AGENT_SLUG = "task_priority"


def _normalize_tags(tags: Any) -> List[str]:
    if isinstance(tags, list):
        return [str(tag).strip() for tag in tags if str(tag).strip()]
    if isinstance(tags, str):
        return [part.strip() for part in tags.split(',') if part.strip()]
    return []


def _compute_score(tags: List[str], due_date: str | None, title: str) -> int:
    score = 45
    tag_set = {t.lower() for t in tags}
    if 'deadline' in tag_set:
        score += 15
    if 'court' in tag_set:
        score += 20
    if 'urgent' in tag_set:
        score += 25
    if 'client_request' in tag_set:
        score += 10
    if due_date:
        try:
            delta = (datetime.strptime(due_date, '%Y-%m-%d').date() - date.today()).days
            if delta <= 1:
                score += 20
            elif delta <= 3:
                score += 12
            elif delta <= 7:
                score += 6
        except ValueError:
            pass
    if 'review' in title.lower():
        score += 5
    return min(score, 100)


def process(request: GenericAgentRequest) -> dict[str, Any]:
    payload = request.payload or {}

    matter = get_matter(payload.get("matter_id"))
    due_date = payload.get("due_date")
    if due_date:
        due_date = date.fromisoformat(due_date)

    score_result = calculate_priority_score(
        due_date=due_date,
        matter_type=(matter or {}).get("matter_type"),
        client_tier=(matter or {}).get("client_tier"),
        tags=payload.get("tags", []),
    )

    task = {
        "title": payload["title"],
        "description": payload.get("description"),
        "matter_id": payload.get("matter_id"),
        "due_date": due_date,
        "priority_score": score_result["priority_score"],
        "status": payload.get("status", "pending"),
        "assigned_to": payload.get("assigned_to"),
        "source": payload.get("source", "manual"),
        "parent_task_id": payload.get("parent_task_id"),
        "tags": payload.get("tags", []),
        "priority_reasoning": score_result["reasoning"],
        "recommended_deadline": score_result["recommended_deadline"],
    }

    saved = insert_task(task)
    sheet_result = sync_task_to_sheet(saved)
    alert_result = maybe_send_high_priority_alert(saved)

    return {
        "status": "ok",
        "task": saved,
        "sheet_sync": sheet_result,
        "alert": alert_result,
    }