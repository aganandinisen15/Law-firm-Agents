from __future__ import annotations

from datetime import date


def calculate_priority_score(
    due_date: date | None,
    matter_type: str | None,
    client_tier: int | None,
    tags: list[str] | None,
) -> dict:
    score = 10
    reasoning = []
    tags = tags or []

    if due_date:
        days_left = (due_date - date.today()).days
        if days_left < 0:
            score += 40
            reasoning.append("Task is overdue")
        elif days_left == 0:
            score += 35
            reasoning.append("Due today")
        elif days_left == 1:
            score += 30
            reasoning.append("Due tomorrow")
        elif days_left <= 3:
            score += 20
            reasoning.append("Due within 3 days")
        elif days_left <= 7:
            score += 10
            reasoning.append("Due within 7 days")

    matter_type = (matter_type or "").lower()
    if matter_type == "litigation":
        score += 20
        reasoning.append("Litigation matter")
    elif matter_type == "corporate":
        score += 10
        reasoning.append("Corporate matter")
    elif matter_type == "real_estate":
        score += 8
        reasoning.append("Real estate matter")
    elif matter_type == "gc_service":
        score += 6
        reasoning.append("GC service matter")

    if client_tier == 1:
        score += 20
        reasoning.append("Tier 1 client")
    elif client_tier == 2:
        score += 10
        reasoning.append("Tier 2 client")

    tag_set = {t.lower() for t in tags}

    if "deadline" in tag_set:
        score += 15
        reasoning.append("Deadline tag")
    if "court" in tag_set:
        score += 20
        reasoning.append("Court tag")
    if "client_request" in tag_set:
        score += 10
        reasoning.append("Client request tag")
    if "urgent" in tag_set:
        score += 25
        reasoning.append("Urgent tag")

    score = max(1, min(score, 100))

    return {
        "priority_score": score,
        "reasoning": ", ".join(reasoning) if reasoning else "Base priority applied",
        "recommended_deadline": due_date.isoformat() if due_date else None,
    }