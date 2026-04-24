from __future__ import annotations


def maybe_send_high_priority_alert(task: dict) -> dict:
    if (task.get("priority_score") or 0) > 80:
        return {
            "status": "alert_created",
            "message": f"High priority task alert for {task['title']}",
        }
    return {
        "status": "skipped",
        "message": "No alert needed",
    }