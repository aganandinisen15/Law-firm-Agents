from shared.legal_agents.schemas import GenericAgentRequest

def process(request: GenericAgentRequest):
    payload = request.payload
    return {
        "summary": "Client intake record prepared.",
        "client_name": payload.get("client_name", "Unknown Client"),
        "matter_type": payload.get("matter_type", "general"),
        "conflicts_status": "manual_review_required",
        "next_steps": ["Run conflicts check", "Draft engagement letter", "Create matter folder"],
        "warnings": []
    }
