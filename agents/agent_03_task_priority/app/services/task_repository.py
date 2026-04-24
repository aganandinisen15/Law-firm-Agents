from __future__ import annotations

from typing import Any
from sqlalchemy import text
from shared.legal_agents.db import engine


def get_matter(matter_id: int | None) -> dict[str, Any] | None:
    if not matter_id:
        return None

    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT matter_id, matter_name, client_name, matter_type, priority_tier, client_tier
                FROM matters
                WHERE matter_id = :matter_id
            """),
            {"matter_id": matter_id},
        ).mappings().first()

    return dict(row) if row else None


def insert_task(task: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                INSERT INTO tasks (
                    title, description, matter_id, due_date, priority_score, status,
                    assigned_to, source, parent_task_id, tags,
                    priority_reasoning, recommended_deadline
                )
                VALUES (
                    :title, :description, :matter_id, :due_date, :priority_score, :status,
                    :assigned_to, :source, :parent_task_id, :tags,
                    :priority_reasoning, :recommended_deadline
                )
                RETURNING task_id, created_at
            """),
            task,
        ).mappings().one()

    task["task_id"] = row["task_id"]
    task["created_at"] = row["created_at"]
    return task


def list_pending_tasks() -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT *
                FROM tasks
                WHERE status IN ('pending', 'in_progress')
                ORDER BY priority_score DESC NULLS LAST, due_date ASC NULLS LAST, created_at ASC
            """)
        ).mappings().all()

    return [dict(r) for r in rows]


def update_task(task_id: int, updates: dict[str, Any]) -> None:
    set_parts = []
    params = {"task_id": task_id}

    for key, value in updates.items():
        set_parts.append(f"{key} = :{key}")
        params[key] = value

    if not set_parts:
        return

    set_parts.append("updated_at = NOW()")

    with engine.begin() as conn:
        conn.execute(
            text(f"""
                UPDATE tasks
                SET {", ".join(set_parts)}
                WHERE task_id = :task_id
            """),
            params,
        )