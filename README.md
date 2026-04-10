# AI Legal Practice System – Email Triage Admin Panel

This package rebuilds the Email Triage & Response Agent as a Gmail-driven admin console.

## What changed

- Gmail is processed server-side through the Gmail API
- the UI does **not** load raw inbox emails into the browser
- the admin panel controls automation, shows watcher status, recent decisions, routing results, and errors
- new inbox emails can be processed automatically by the backend watcher
- triage results route into task creation, meeting scheduling, deadline creation, Gmail labeling, archiving, and draft creation

## Run

```bash
docker compose up -d postgres
docker compose up --build email-triage task-priority calendar-scheduling
```

Open `http://localhost:8011/`.

See `agents/agent_01_email_triage/README.md` for Gmail scope and refresh-token setup.
