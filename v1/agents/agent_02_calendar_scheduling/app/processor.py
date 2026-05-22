from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy import text

from shared.legal_agents.adapters import GoogleWorkspaceAdapter
from shared.legal_agents.db import engine
from shared.legal_agents.db_utils import log_audit, log_error
from shared.legal_agents.schemas import GenericAgentRequest

AGENT_SLUG = "calendar_scheduling"
gw = GoogleWorkspaceAdapter()

WEEKDAY_MAP = {
    'monday': 0,
    'tuesday': 1,
    'wednesday': 2,
    'thursday': 3,
    'friday': 4,
}


def _next_weekday(target: int, hour: int = 10) -> str:
    today = datetime.now()
    days_ahead = (target - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    candidate = (today + timedelta(days=days_ahead)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return candidate.isoformat(timespec='minutes')


def _parse_request_text(request_text: str) -> Dict[str, Any]:
    text_value = (request_text or '').strip()
    lower = text_value.lower()
    proposed_times: List[str] = []
    for weekday, index in WEEKDAY_MAP.items():
        if weekday in lower:
            proposed_times.append(_next_weekday(index, 10 if 'morning' in lower else 14))
    if not proposed_times:
        proposed_times = [
            _next_weekday(1, 10),
            _next_weekday(2, 14),
            _next_weekday(3, 11),
        ]
    return {
        'title': 'Client Follow-up Meeting' if 'client' in lower else 'Matter Meeting',
        'attendees': [],
        'proposed_times': proposed_times,
        'duration_minutes': 30 if '30' in lower else 60,
        'location': 'Video call' if any(k in lower for k in ['zoom', 'video', 'call', 'meet']) else 'TBD',
        'notes': text_value,
    }


def process(request: GenericAgentRequest):
    payload = request.payload
    correlation_id = request.correlation_id
    working_payload = dict(payload)
    if payload.get('request_text') and not payload.get('proposed_times'):
        working_payload.update(_parse_request_text(str(payload.get('request_text'))))

    attendees = working_payload.get('attendees', [])
    proposed_times = working_payload.get('proposed_times', [])
    availability = gw.check_calendar(attendees, proposed_times)
    result = {
        'summary': 'Scheduling request analyzed.',
        'title': working_payload.get('title', 'Meeting'),
        'available_slots': availability['available'],
        'conflicts': availability['conflicts'],
        'next_action': 'create_event' if availability['available'] else 'send_alternatives',
        'warnings': []
    }
    if availability['available']:
        event_preview = gw.create_event(working_payload.get('title', 'Meeting'), availability['available'][0], attendees)
        result['event_preview'] = event_preview
        try:
            with engine.begin() as conn:
                row = conn.execute(
                    text(
                        '''
                        INSERT INTO meetings (title, attendees, scheduled_time, duration, calendar_event_id, status)
                        VALUES (:title, CAST(:attendees AS JSONB), :scheduled_time, :duration, :calendar_event_id, :status)
                        RETURNING meeting_id, created_at
                        '''
                    ),
                    {
                        'title': event_preview['title'],
                        'attendees': json.dumps(attendees),
                        'scheduled_time': event_preview['when'],
                        'duration': int(working_payload.get('duration_minutes') or 60),
                        'calendar_event_id': event_preview['calendar_event_id'],
                        'status': 'tentative',
                    },
                ).mappings().one()
                result['meeting_id'] = row['meeting_id']
            log_audit(AGENT_SLUG, 'meeting_created', correlation_id, {'meeting_id': result['meeting_id'], 'title': event_preview['title']})
        except Exception as exc:  # pragma: no cover
            result['warnings'].append(str(exc))
            log_error(AGENT_SLUG, correlation_id, str(exc), working_payload)
    return result
