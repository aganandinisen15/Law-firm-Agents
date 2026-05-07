from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from shared.legal_agents.adapters import AnthropicAdapter
from shared.legal_agents.db import engine
from shared.legal_agents.schemas import GenericAgentRequest
from shared.legal_agents.settings import settings

BASE_DIR = Path(__file__).resolve().parent
LOCAL_DRIVE_ROOT = Path(os.getenv("DOCUMENT_LOCAL_DRIVE_ROOT", BASE_DIR.parent / "local_drive"))
ROOT_FOLDER_NAME = os.getenv("DOCUMENT_ROOT_FOLDER", "Law Firm Documents")
MANUAL_REVIEW_FOLDER = "Inbox - Needs Filing/Needs Manual Review"
DEADLINE_AGENT_URL = os.getenv("DEADLINE_AGENT_URL", "http://deadline-tracking:8016/run")

DOC_TYPE_TO_FOLDER = {
    "engagement": "01 - Engagement & Billing",
    "billing": "01 - Engagement & Billing",
    "correspondence": "02 - Correspondence",
    "letter": "02 - Correspondence",
    "email": "02 - Correspondence",
    "complaint": "03 - Pleadings",
    "answer": "03 - Pleadings",
    "motion": "03 - Pleadings",
    "pleading": "03 - Pleadings",
    "discovery": "04 - Discovery",
    "contract": "05 - Contracts & Agreements",
    "agreement": "05 - Contracts & Agreements",
    "research_memo": "06 - Legal Research",
    "research": "06 - Legal Research",
    "memo": "07 - Work Product",
    "work_product": "07 - Work Product",
    "court_order": "08 - Court Orders",
    "order": "08 - Court Orders",
    "misc": "09 - Miscellaneous",
}

SYSTEM_PROMPT = """You are a legal document classification expert. Analyze documents and determine proper filing.
Return strict JSON only. No markdown."""


def _clean_segment(value: Any, fallback: str = "Unknown") -> str:
    value = str(value or fallback).strip()
    value = re.sub(r"[^A-Za-z0-9]+", "", value)
    return value or fallback


def _safe_folder(value: Any, fallback: str = "Unknown") -> str:
    value = str(value or fallback).strip()
    value = re.sub(r"[\\/:*?\"<>|]+", "-", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or fallback


def _parse_date(value: Any) -> str:
    if not value:
        return date.today().isoformat()
    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%B %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", value)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return date.today().isoformat()


def _guess_doc_type(filename: str, text_value: str) -> str:
    haystack = f"{filename}\n{text_value}".lower()
    rules = [
        ("court_order", ["order", "ordered by the court", "judge"]),
        ("complaint", ["complaint", "plaintiff", "cause of action"]),
        ("answer", ["answer", "defendant answers"]),
        ("motion", ["motion", "summary judgment", "dismiss"]),
        ("contract", ["agreement", "contract", "terms and conditions"]),
        ("discovery", ["interrogatories", "request for production", "discovery"]),
        ("research_memo", ["legal research", "memorandum", "case law"]),
        ("correspondence", ["dear", "sincerely", "regards"]),
    ]
    for doc_type, words in rules:
        if any(word in haystack for word in words):
            return doc_type
    return "misc"


def _guess_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    filename = payload.get("original_filename") or payload.get("filename") or "document.pdf"
    extracted_text = payload.get("extracted_text") or payload.get("text") or payload.get("first_2_pages_text") or ""
    doc_type = payload.get("document_type") or _guess_doc_type(filename, extracted_text)
    client_name = payload.get("client_name") or _extract_after_label(extracted_text, "client") or "Unknown Client"
    matter_name = payload.get("matter_name") or _extract_case_name(extracted_text) or payload.get("case_number") or "Unknown Matter"
    doc_date = _parse_date(payload.get("document_date") or _extract_date(extracted_text))
    deadline_date = _extract_deadline(extracted_text)
    confidence = 8 if client_name != "Unknown Client" and matter_name != "Unknown Matter" else 5
    return {
        "document_type": doc_type,
        "client_name": client_name,
        "matter_name": matter_name,
        "case_number": payload.get("case_number") or _extract_case_number(extracted_text),
        "document_date": doc_date,
        "key_parties": payload.get("key_parties") or _extract_parties(extracted_text),
        "suggested_description": payload.get("description") or payload.get("suggested_description") or _description_from_filename(filename),
        "contains_deadline": bool(deadline_date),
        "deadline_date": deadline_date,
        "confidence_score": confidence,
    }


def _extract_after_label(text_value: str, label: str) -> str | None:
    match = re.search(rf"{label}\s*[:\-]\s*([^\n,;]+)", text_value or "", re.I)
    return match.group(1).strip() if match else None


def _extract_case_name(text_value: str) -> str | None:
    match = re.search(r"([A-Z][A-Za-z0-9 .,&'-]+\s+v\.?\s+[A-Z][A-Za-z0-9 .,&'-]+)", text_value or "")
    return match.group(1).strip() if match else None


def _extract_case_number(text_value: str) -> str | None:
    match = re.search(r"(?:case|civil action|docket)\s*(?:no\.|number|#)?\s*[:\-]?\s*([A-Za-z0-9:.-]+)", text_value or "", re.I)
    return match.group(1).strip() if match else None


def _extract_date(text_value: str) -> str | None:
    patterns = [
        r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2})\b",
        r"\b(\d{1,2}[-/]\d{1,2}[-/]20\d{2})\b",
        r"\b([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text_value or "")
        if match:
            return match.group(1)
    return None


def _extract_deadline(text_value: str) -> str | None:
    lower = text_value or ""
    if not re.search(r"deadline|due|respond by|file by|hearing on", lower, re.I):
        return None
    return _parse_date(_extract_date(lower)) if _extract_date(lower) else None


def _extract_parties(text_value: str) -> list[str]:
    case = _extract_case_name(text_value)
    if case and " v" in case.lower():
        return [p.strip(" .") for p in re.split(r"\s+v\.?\s+", case, flags=re.I) if p.strip()]
    return []


def _description_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"[_-]+", " ", stem).strip().title()
    return stem or "Filed Document"


def _classify_with_claude(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not getattr(settings, "anthropic_api_key", None):
        return None
    try:
        adapter = AnthropicAdapter(settings.anthropic_api_key, settings.anthropic_model)
        filename = payload.get("original_filename") or payload.get("filename") or "document.pdf"
        file_type = payload.get("file_type") or Path(filename).suffix.lstrip(".") or "unknown"
        extracted_text = (payload.get("first_2_pages_text") or payload.get("extracted_text") or payload.get("text") or "")[:8000]
        user_prompt = f"""<document>
<filename>{filename}</filename>
<file_type>{file_type}</file_type>
<extracted_text>{extracted_text}</extracted_text>
</document>
Analyze and return JSON with document_type, client_name, matter_name, case_number, document_date, key_parties, suggested_description, contains_deadline, deadline_date, confidence_score."""
        return adapter.json_completion(SYSTEM_PROMPT, user_prompt)
    except Exception:
        return None


def _find_or_create_matter(client_name: str, matter_name: str) -> dict[str, Any]:
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT matter_id, client_name, matter_name
                FROM matters
                WHERE lower(client_name)=lower(:client_name)
                  AND lower(matter_name)=lower(:matter_name)
                LIMIT 1
            """),
            {"client_name": client_name, "matter_name": matter_name},
        ).mappings().first()
        if row:
            return {"created": False, **dict(row)}
        created = conn.execute(
            text("""
                INSERT INTO matters (client_name, matter_name, matter_type, opened_date, status, billing_type, priority_tier)
                VALUES (:client_name, :matter_name, 'general', CURRENT_DATE, 'active', 'hourly', 3)
                RETURNING matter_id, client_name, matter_name
            """),
            {"client_name": client_name, "matter_name": matter_name},
        ).mappings().one()
        return {"created": True, **dict(created)}


def _folder_for_doc_type(doc_type: str) -> str:
    return DOC_TYPE_TO_FOLDER.get(str(doc_type or "misc").lower(), "09 - Miscellaneous")


def _target_folder(analysis: dict[str, Any], manual_review: bool = False) -> Path:
    root = LOCAL_DRIVE_ROOT / ROOT_FOLDER_NAME
    if manual_review:
        return root / MANUAL_REVIEW_FOLDER
    return (
        root
        / "Clients"
        / _safe_folder(analysis.get("client_name"), "Unknown Client")
        / _safe_folder(analysis.get("matter_name"), "Unknown Matter")
        / _folder_for_doc_type(analysis.get("document_type", "misc"))
    )


def _build_filename(analysis: dict[str, Any], original_filename: str) -> str:
    ext = Path(original_filename or "document.pdf").suffix or ".pdf"
    doc_date = _parse_date(analysis.get("document_date"))
    matter = _clean_segment(analysis.get("matter_name"), "UnknownMatter")
    doc_type = _clean_segment(analysis.get("document_type"), "Misc")
    description = _clean_segment(analysis.get("suggested_description"), "FiledDocument")
    return f"{doc_date}_{matter}_{doc_type}_{description}{ext.lower()}"


def _dedupe_path(folder: Path, filename: str) -> Path:
    candidate = folder / filename
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    version = 2
    while True:
        candidate = folder / f"{stem}_v{version}{suffix}"
        if not candidate.exists():
            return candidate
        version += 1


def _file_hash(source_path: str | None, text_value: str) -> str:
    h = hashlib.sha256()
    if source_path and Path(source_path).exists():
        with open(source_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
    else:
        h.update((text_value or "").encode("utf-8"))
    return h.hexdigest()


def _move_or_stub_file(source_path: str | None, destination: Path, extracted_text: str) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source_path and Path(source_path).exists():
        shutil.copy2(source_path, destination)
        return {"status": "copied", "path": str(destination)}
    destination.write_text(extracted_text or "Document placeholder created by Document Organization Agent. Original file was not available locally.", encoding="utf-8")
    return {"status": "placeholder_created", "path": str(destination)}


def _index_document(filename: str, matter_id: int | None, analysis: dict[str, Any], file_path: str, extracted_text: str, file_hash: str, file_size: int | None) -> int | None:
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("""
                    INSERT INTO document_index (
                        filename, matter_id, doc_type, file_path, doc_date, extracted_text,
                        parties, contains_deadline, deadline_date, file_size, file_hash
                    ) VALUES (
                        :filename, :matter_id, :doc_type, :file_path, :doc_date, :extracted_text,
                        CAST(:parties AS JSONB), :contains_deadline, :deadline_date, :file_size, :file_hash
                    )
                    RETURNING doc_id
                """),
                {
                    "filename": filename,
                    "matter_id": matter_id,
                    "doc_type": analysis.get("document_type"),
                    "file_path": file_path,
                    "doc_date": _parse_date(analysis.get("document_date")),
                    "extracted_text": extracted_text,
                    "parties": json.dumps(analysis.get("key_parties") or []),
                    "contains_deadline": bool(analysis.get("contains_deadline")),
                    "deadline_date": analysis.get("deadline_date"),
                    "file_size": file_size,
                    "file_hash": file_hash,
                },
            ).mappings().one()
            return row["doc_id"]
    except Exception:
        return None


def _trigger_deadline_agent(analysis: dict[str, Any], doc_id: int | None, filename: str) -> dict[str, Any] | None:
    if not analysis.get("contains_deadline") or not analysis.get("deadline_date"):
        return None
    try:
        import requests

        response = requests.post(
            DEADLINE_AGENT_URL,
            json={
                "payload": {
                    "deadline_date": analysis.get("deadline_date"),
                    "deadline_type": "document",
                    "description": f"Deadline from {filename}",
                    "source": "document_organization",
                    "doc_id": doc_id,
                }
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {"status": "deadline_agent_error", "error": str(exc)}


def process(request: GenericAgentRequest):
    payload = request.payload or {}
    original_filename = payload.get("original_filename") or payload.get("filename") or "document.pdf"
    extracted_text = payload.get("extracted_text") or payload.get("first_2_pages_text") or payload.get("text") or ""
    source_path = payload.get("source_path") or payload.get("local_path")

    analysis = _classify_with_claude(payload) or _guess_analysis(payload)
    analysis["document_date"] = _parse_date(analysis.get("document_date"))
    analysis["confidence_score"] = int(analysis.get("confidence_score") or 5)
    analysis["document_type"] = str(analysis.get("document_type") or "misc").lower()

    warnings: list[str] = []
    manual_review = analysis["confidence_score"] < 7 or not analysis.get("client_name") or not analysis.get("matter_name")
    matter = None
    if manual_review:
        warnings.append("Low classification confidence or missing client/matter; filed to Needs Manual Review.")
    else:
        matter = _find_or_create_matter(analysis["client_name"], analysis["matter_name"])

    target_folder = _target_folder(analysis, manual_review=manual_review)
    target_folder.mkdir(parents=True, exist_ok=True)

    new_filename = _build_filename(analysis, original_filename)
    destination = _dedupe_path(target_folder, new_filename)
    file_hash = _file_hash(source_path, extracted_text)
    movement = _move_or_stub_file(source_path, destination, extracted_text)
    file_size = destination.stat().st_size if destination.exists() else payload.get("file_size")

    doc_id = _index_document(
        filename=destination.name,
        matter_id=matter.get("matter_id") if matter else None,
        analysis=analysis,
        file_path=str(destination),
        extracted_text=extracted_text,
        file_hash=file_hash,
        file_size=file_size,
    )
    deadline_result = _trigger_deadline_agent(analysis, doc_id, destination.name)

    return {
        "summary": "Document filed, renamed, and indexed." if not manual_review else "Document routed for manual filing review.",
        "document_analysis": analysis,
        "document_type": analysis.get("document_type"),
        "client_name": analysis.get("client_name"),
        "matter_name": analysis.get("matter_name"),
        "matter": matter,
        "manual_review": manual_review,
        "renamed_file": destination.name,
        "target_folder": str(target_folder),
        "file_path": str(destination),
        "file_movement": movement,
        "doc_id": doc_id,
        "file_hash": file_hash,
        "deadline_triggered": deadline_result is not None,
        "deadline_result": deadline_result,
        "warnings": warnings,
    }
