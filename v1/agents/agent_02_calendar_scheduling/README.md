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


## Fixes included in this build
- preferred date is honored first (for example, "schedule on 18th" schedules on the 18th if free)
- correct Google Calendar time zone handling
- correct availability window handling without invalid UTC suffixing
- real Google event creation returns event ID and event link
- Google Calendar auth is separated from Gmail draft auth so calendar creation still works even if Gmail compose scope is unavailable
- clearer Google status reporting in overview API

## OAuth scopes
Generate the refresh token with at least this scope for live calendar creation:
- `https://www.googleapis.com/auth/calendar`

Optional Gmail draft support uses:
- `https://www.googleapis.com/auth/gmail.compose`

If you want only Calendar working first, use a refresh token that includes only the Calendar scope.
