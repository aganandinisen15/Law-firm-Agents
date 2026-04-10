from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy import text

from .db import engine

logger = logging.getLogger(__name__)


def log_audit(agent_slug: str, action: str, correlation_id: Optional[str], payload: Dict[str, Any]) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO audit_log (agent_slug, action, correlation_id, payload)
                    VALUES (:agent_slug, :action, :correlation_id, CAST(:payload AS JSONB))
                    """
                ),
                {
                    "agent_slug": agent_slug,
                    "action": action,
                    "correlation_id": correlation_id,
                    "payload": json.dumps(payload, default=str),
                },
            )
    except Exception as exc:  # pragma: no cover - best effort logging
        logger.warning("audit log insert failed: %s", exc)


def log_error(agent_slug: str, correlation_id: Optional[str], error_message: str, payload: Dict[str, Any]) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO error_log (agent_slug, correlation_id, error_message, payload)
                    VALUES (:agent_slug, :correlation_id, :error_message, CAST(:payload AS JSONB))
                    """
                ),
                {
                    "agent_slug": agent_slug,
                    "correlation_id": correlation_id,
                    "error_message": error_message,
                    "payload": json.dumps(payload, default=str),
                },
            )
    except Exception as exc:  # pragma: no cover - best effort logging
        logger.warning("error log insert failed: %s", exc)
