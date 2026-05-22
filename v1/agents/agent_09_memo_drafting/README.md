# Memo Drafting Agent

## Purpose
Draft memos from verified research results only.

## Local run
```bash
PYTHONPATH=. uvicorn agents.agent_09_memo_drafting.app.main:app --host 0.0.0.0 --port 8019
```

## Endpoints
- `GET /health`
- `POST /run`

## Sample payload
See `samples/request.json`.

## Notes
This folder is intentionally independent so the agent can run by itself or through n8n.
