from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List

from sqlalchemy import text

from shared.legal_agents.db import engine
from shared.legal_agents.db_utils import log_audit, log_error
from shared.legal_agents.schemas import GenericAgentRequest

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


def process(request: GenericAgentRequest):
    payload: Dict[str, Any] = request.payload
    title = str(payload.get('title') or 'Follow up task').strip()
    description = str(payload.get('description') or '').strip()
    due_date = payload.get('due_date') or None
    tags = _normalize_tags(payload.get('tags', []))
    priority_score = _compute_score(tags, due_date, title)
    correlation_id = request.correlation_id

    task_id = None
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    '''
                    INSERT INTO tasks (title, description, due_date, priority_score, status, assigned_to, source, tags)
                    VALUES (:title, :description, :due_date, :priority_score, :status, :assigned_to, :source, :tags)
                    RETURNING task_id, created_at
                    '''
                ),
                {
                    'title': title,
                    'description': description,
                    'due_date': due_date,
                    'priority_score': priority_score,
                    'status': 'pending',
                    'assigned_to': payload.get('assigned_to') or 'attorney',
                    'source': payload.get('source') or 'dashboard',
                    'tags': tags,
                },
            ).mappings().one()
            task_id = row['task_id']
        log_audit(AGENT_SLUG, 'task_created', correlation_id, {'task_id': task_id, 'title': title, 'priority_score': priority_score})
    except Exception as exc:  # pragma: no cover
        log_error(AGENT_SLUG, correlation_id, str(exc), payload)
        return {
            'summary': 'Task processing failed.',
            'warnings': [str(exc)],
            'title': title,
            'priority_score': priority_score,
            'recommended_deadline': due_date,
        }

    return {
        'summary': 'Task created and prioritized.',
        'task_id': task_id,
        'title': title,
        'priority_score': priority_score,
        'recommended_deadline': due_date,
        'today': str(date.today()),
        'tags': tags,
        'warnings': []
    }
