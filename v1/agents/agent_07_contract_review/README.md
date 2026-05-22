# Contract Review Agent

## Purpose
Review contracts against playbook, flag issues, and generate comments.

## Local run
```bash
PYTHONPATH=. uvicorn agents.agent_07_contract_review.app.main:app --host 0.0.0.0 --port 8017
```

## Endpoints
- `GET /health`
- `POST /run`

## Sample payload
See `samples/request.json`.

## Notes
This folder is intentionally independent so the agent can run by itself or through n8n.
