Minimal admin panel UI included at http://localhost:8012/\n\n# Agent 02 - Calendar & Scheduling Agent

A standalone regenerated scheduling agent with:
- FastAPI backend
- Admin panel UI
- Meeting detail extraction
- Calendar availability checking
- Conflict handling with alternative slots
- Google Calendar event creation
- Gmail draft creation for conflict alternatives
- SQLite logging for meetings, tasks, and runs

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8012
```

Open: http://localhost:8012/

## Run with Docker

```bash
docker build -t calendar-agent .
docker run --rm -p 8012:8012 --env-file .env calendar-agent
```

## Google API setup

Use one matching OAuth client for all three values below:
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`

The agent uses:
- Google Calendar API to check availability and create events
- Gmail API to create draft replies with alternative time options

If env vars are missing, the agent runs in deterministic fallback mode so you can still test the workflow and UI.

## API routes
- `GET /health`
- `GET /api/overview`
- `POST /run`
- `GET /`

## Test

```bash
curl -X POST http://localhost:8012/run \
  -H "Content-Type: application/json" \
  -d @samples/request.json
```
