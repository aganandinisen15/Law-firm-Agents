# Document Organization Agent

## Purpose
Classify, rename, and route documents into matter folders.

## Local run
```bash
PYTHONPATH=. uvicorn agents.agent_04_document_organization.app.main:app --host 0.0.0.0 --port 8014
```

## Endpoints
- `GET /health`
- `POST /run`

## Sample payload
See `samples/request.json`.

## Notes
This folder is intentionally independent so the agent can run by itself or through n8n.
