# Task & Priority Management Agent

## Purpose
Create tasks, calculate priority, and generate daily plans.

## Local run
```bash
PYTHONPATH=. uvicorn agents.agent_03_task_priority.app.main:app --host 0.0.0.0 --port 8013
```

## Endpoints
- `GET /health`
- `POST /run`

## Sample payload
See `samples/request.json`.

## Notes
This folder is intentionally independent so the agent can run by itself or through n8n.
