# Agent 4: Document Organization Agent

Automatically classifies legal documents, creates the standard matter folder path, renames files, indexes text in `document_index`, and triggers the deadline agent when a deadline is detected.

## Main routes

- `POST /run` - generic agent route
- `POST /api/documents/file` - classify, file, rename, and index a document
- `POST /api/documents/from-email` - same workflow for email attachments
- `GET /api/documents` - recent indexed documents
- `GET /api/search?q=smith` - full-text style search over filename, extracted text, client, and matter
- `GET /api/overview` - metrics and recent documents

## Payload

```json
{
  "filename": "Initial Complaint.pdf",
  "file_type": "pdf",
  "extracted_text": "first two pages or OCR text here",
  "source_path": "/optional/local/file/path.pdf",
  "client_name": "optional override",
  "matter_name": "optional override"
}
```

If `source_path` is not available, the service creates a placeholder local file so the flow remains testable without Google Drive credentials.

## Local storage fallback

Files are written under:

```text
agents/agent_04_document_organization/local_drive/Law Firm Documents/
```

Set `DOCUMENT_LOCAL_DRIVE_ROOT` to change this. A Google Drive implementation can replace the local file movement layer later without changing the API contract.

## Environment

```env
DEADLINE_AGENT_URL=http://deadline-tracking:8016/run
DOCUMENT_LOCAL_DRIVE_ROOT=/app/document_drive
DOCUMENT_ROOT_FOLDER=Law Firm Documents
```
