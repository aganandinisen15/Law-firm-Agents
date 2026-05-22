from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from shared.legal_agents.base_agent import build_router
from shared.legal_agents.db import engine
from shared.legal_agents.logging_utils import configure_logging
from shared.legal_agents.schemas import GenericAgentRequest
from shared.legal_agents.settings import settings
from .processor import process

configure_logging(settings.log_level)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Document Organization Agent", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(build_router("document_organization", "Document Organization Agent", process))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "agent": "document_organization"}


@app.post("/api/documents/file")
def file_document(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        result = process(GenericAgentRequest(payload=payload))
        return {"status": "ok", **result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Document filing failed: {exc}")


@app.post("/api/documents/from-email")
def file_email_attachment(payload: dict[str, Any]) -> dict[str, Any]:
    payload = {**payload, "source": payload.get("source") or "email_attachment"}
    return file_document(payload)


@app.get("/api/documents")
def list_documents(limit: int = 20) -> dict[str, Any]:
    safe_limit = min(max(limit, 1), 100)
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT d.doc_id, d.filename, d.doc_type, d.file_path, d.upload_date, d.doc_date,
                       d.contains_deadline, d.deadline_date, d.file_size, d.file_hash,
                       m.client_name, m.matter_name
                FROM document_index d
                LEFT JOIN matters m ON d.matter_id = m.matter_id
                ORDER BY d.upload_date DESC NULLS LAST, d.doc_id DESC
                LIMIT :limit
            """),
            {"limit": safe_limit},
        ).mappings().all()
    return {"status": "ok", "items": [dict(row) for row in rows]}


@app.get("/api/search")
def search_documents(q: str, limit: int = 20) -> dict[str, Any]:
    safe_limit = min(max(limit, 1), 100)
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT d.doc_id, d.filename, d.doc_type, d.file_path, d.doc_date,
                       m.client_name, m.matter_name
                FROM document_index d
                LEFT JOIN matters m ON d.matter_id = m.matter_id
                WHERE d.filename ILIKE :query
                   OR d.extracted_text ILIKE :query
                   OR m.client_name ILIKE :query
                   OR m.matter_name ILIKE :query
                ORDER BY d.upload_date DESC NULLS LAST, d.doc_id DESC
                LIMIT :limit
            """),
            {"query": f"%{q}%", "limit": safe_limit},
        ).mappings().all()
    return {"status": "ok", "items": [dict(row) for row in rows]}


@app.get("/api/overview")
def overview() -> dict[str, Any]:
    with engine.begin() as conn:
        metrics = conn.execute(
            text("""
                SELECT COUNT(*) AS total_documents,
                       COUNT(*) FILTER (WHERE contains_deadline IS TRUE) AS documents_with_deadlines,
                       COUNT(*) FILTER (WHERE matter_id IS NULL) AS manual_review_documents
                FROM document_index
            """)
        ).mappings().one()
        recent = conn.execute(
            text("""
                SELECT d.doc_id, d.filename, d.doc_type, d.file_path, d.upload_date,
                       m.client_name, m.matter_name
                FROM document_index d
                LEFT JOIN matters m ON d.matter_id = m.matter_id
                ORDER BY d.upload_date DESC NULLS LAST, d.doc_id DESC
                LIMIT 8
            """)
        ).mappings().all()
    return {"status": "ok", "metrics": dict(metrics), "recent_documents": [dict(row) for row in recent]}


@app.get("/", response_class=HTMLResponse)
def root(_: Request):
    return """
    <html><body>
      <h1>Document Organization Agent</h1>
      <p>Use POST /api/documents/file to classify, rename, file, and index documents.</p>
    </body></html>
    """
