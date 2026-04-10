# Calendar & Scheduling Agent

## Purpose
Extract meeting details, check availability, and prepare scheduling actions.

## Local run
```bash
PYTHONPATH=. uvicorn agents.agent_02_calendar_scheduling.app.main:app --host 0.0.0.0 --port 8012
```

## Endpoints
- `GET /health`
- `POST /run`

## Sample payload
See `samples/request.json`.

## Notes
This folder is intentionally independent so the agent can run by itself or through n8n.
