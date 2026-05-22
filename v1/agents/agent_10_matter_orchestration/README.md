# Matter Orchestration Agent

## Purpose
Aggregate matter activity, build summaries, and drive weekly reports.

## Local run
```bash
PYTHONPATH=. uvicorn agents.agent_10_matter_orchestration.app.main:app --host 0.0.0.0 --port 8020
```

## Endpoints
- `GET /health`
- `POST /run`

## Sample payload
See `samples/request.json`.

## Notes
This folder is intentionally independent so the agent can run by itself or through n8n.
