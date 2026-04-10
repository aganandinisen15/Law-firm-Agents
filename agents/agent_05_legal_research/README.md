# Legal Research Agent

## Purpose
Run verified legal research using LexisNexis-only citation pipeline.

## Local run
```bash
PYTHONPATH=. uvicorn agents.agent_05_legal_research.app.main:app --host 0.0.0.0 --port 8015
```

## Endpoints
- `GET /health`
- `POST /run`

## Sample payload
See `samples/request.json`.

## Notes
This folder is intentionally independent so the agent can run by itself or through n8n.
