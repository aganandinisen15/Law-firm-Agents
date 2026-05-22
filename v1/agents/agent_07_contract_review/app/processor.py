from shared.legal_agents.schemas import GenericAgentRequest

CHECKS = [
    "Indemnification provisions",
    "Limitation of liability",
    "Termination rights",
    "Payment terms",
    "IP ownership",
    "Jurisdiction and venue",
    "Force majeure",
    "Notice provisions",
]

def process(request: GenericAgentRequest):
    return {
        "summary": "Contract review checklist generated.",
        "checks_run": CHECKS,
        "risk_level": "MEDIUM",
        "suggested_next_step": "Upload playbook and contract text for clause-level review.",
        "warnings": []
    }
