# Agent 01 – Email Triage & Response Admin Console

This version implements the Email Triage & Response Agent from the developer brief as an **admin panel**, not an inbox reader UI.

## Admin panel

Open:

```text
http://localhost:8011/
```

What the admin panel does:
- start and stop the Gmail watcher
- run a one-time inbox check without exposing raw Gmail messages in the browser
- show processing totals, urgent counts, drafts, routed tasks, meetings, and errors
- simulate single emails for testing
- display the latest workflow output and recent processed decisions

## Gmail configuration

Set these values in `.env`:

```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
GMAIL_MAILBOX_USER=me
GMAIL_DEFAULT_QUERY=in:inbox -category:promotions -category:social
```

### Required Gmail scopes

Generate the refresh token with these scopes:

```python
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
]
```

`gmail.readonly` reads inbox metadata/body, `gmail.modify` applies labels and archives processed emails, and `gmail.compose` creates attorney-review drafts in Gmail.

A helper script is included at `scripts/get_gmail_refresh_token.py`.

## Run

```bash
docker compose up -d postgres
docker compose up --build email-triage task-priority calendar-scheduling
```

## Main endpoints

- `/` admin panel
- `/run` base agent endpoint
- `/api/admin/overview` panel data
- `/api/admin/automation/start` start backend Gmail watcher
- `/api/admin/automation/stop` stop backend Gmail watcher
- `/api/admin/automation/run-once` process the latest eligible inbox email now
- `/api/admin/manual/triage` manual triage test
- `/api/admin/manual/workflow` manual triage + routing test
- `/api/history` processed email history
- `/api/tasks` recent tasks
- `/api/meetings` recent meetings

## Current workflow

1. Poll Gmail for inbox messages matching the configured query
2. Skip already processed email IDs
3. Categorize and prioritize the email
4. Create a draft response when needed
5. Apply Gmail labels and archive the message
6. Trigger tasks, scheduling, and deadline creation based on routing logic
7. Record everything in PostgreSQL for review
