# Client Intake Agent

## Purpose
Process intake forms, run conflicts checks, and draft onboarding materials.

## Local run
```bash
PYTHONPATH=. uvicorn agents.agent_08_client_intake.app.main:app --host 0.0.0.0 --port 8018
```

## Endpoints
- `GET /health`
- `POST /run`

## Sample payload
See `samples/request.json`.

## Notes
This folder is intentionally independent so the agent can run by itself or through n8n.
