from shared.legal_agents.schemas import GenericAgentRequest

def process(request: GenericAgentRequest):
    payload = request.payload
    return {
        "summary": "Matter dashboard payload generated.",
        "matter_name": payload.get("matter_name", "Unknown Matter"),
        "widgets": [
            "status",
            "upcoming_deadlines",
            "active_tasks",
            "recent_documents",
            "outstanding_client_requests",
            "budget_vs_actual",
        ],
        "warnings": []
    }
