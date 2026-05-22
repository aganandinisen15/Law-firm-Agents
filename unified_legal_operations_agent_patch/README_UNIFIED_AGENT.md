# Unified Legal Operations Agent

This patch combines the first four agents into one FastAPI service:

- Agent 1: Email Triage
- Agent 2: Calendar Scheduling
- Agent 3: Task Priority
- Agent 4: Document Organization

The unified app runs on port `8011` and serves one shared frontend.

## Install patch

Copy the `agents/unified_legal_operations` folder and `docker-compose.unified.yml` into your project root.

## Run

```bash
docker compose -f docker-compose.unified.yml down
docker compose -f docker-compose.unified.yml up --build
```

Open:

```text
http://localhost:8011
```

## Test health

```bash
curl http://localhost:8011/health
```

## Test email workflow

```bash
curl -X POST http://localhost:8011/api/admin/manual/workflow \
  -H "Content-Type: application/json" \
  -d '{
    "from":"client@example.com",
    "subject":"SCHEDULE: Review complaint",
    "body":"Please schedule a video call next Tuesday at 10am. Also review the attached complaint.",
    "attachments":[{"filename":"complaint.pdf","file_type":"pdf","extracted_text":"Complaint Smith v Jones filed on 2026-01-15."}]
  }'
```

## Test calendar

```bash
curl -X POST http://localhost:8011/api/calendar/schedule \
  -H "Content-Type: application/json" \
  -d '{"request_text":"Schedule a meeting on 25 April 2026 at 3pm with client@example.com", "auto_create_event": true}'
```

## Test task

```bash
curl -X POST http://localhost:8011/api/tasks/create \
  -H "Content-Type: application/json" \
  -d '{"title":"Prepare filing", "description":"Prepare court filing", "due_date":"2026-05-20", "tags":["court","urgent"]}'
```

## Test document filing

```bash
curl -X POST http://localhost:8011/api/documents/file \
  -H "Content-Type: application/json" \
  -d '{"original_filename":"complaint.pdf", "file_type":"pdf", "client_name":"Smith", "matter_name":"Smith v Jones", "document_type":"complaint", "extracted_text":"Complaint filed by Smith against Jones."}'
```

## Important

Use this compose file instead of the microservice compose when you want one combined agent. Do not run both at the same time on port `8011`.
