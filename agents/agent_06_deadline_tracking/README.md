# Deadline Tracking Agent

## Purpose
Extract deadlines, create reminders, and escalate risks.

## Local run
```bash
PYTHONPATH=. uvicorn agents.agent_06_deadline_tracking.app.main:app --host 0.0.0.0 --port 8016
```

## Endpoints
- `GET /health`
- `POST /run`

## Sample payload
See `samples/request.json`.

## Notes
This folder is intentionally independent so the agent can run by itself or through n8n.
